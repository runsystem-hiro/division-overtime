from __future__ import annotations

import secrets
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

import requests

from .database import Database
from .employee_repository import EmployeeRepository, ManagedEmployee
from .employees import EmployeeDataError, load_employees, write_employees


class KotEmployeeSyncError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class KotEmployee:
    code: str
    key: str
    last_name: str
    first_name: str
    email: str
    division_code: str
    division_name: str
    group_codes: tuple[str, ...]
    group_names: tuple[str, ...]
    resignation_date: str


class KotEmployeeSource(Protocol):
    def fetch(self) -> list[KotEmployee]: ...


@dataclass(frozen=True, slots=True)
class SyncDifference:
    code: str
    action: str
    current: dict[str, object] | None
    proposed: dict[str, object] | None
    warnings: tuple[str, ...]
    changed_fields: tuple[str, ...] = ()


@dataclass(slots=True)
class _Preview:
    created_at: float
    employees: dict[str, KotEmployee]
    differences: list[SyncDifference]
    fetched_count: int
    target_count: int


class KotEmployeeClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        connect_timeout: float,
        read_timeout: float,
        retry_count: int,
        retry_backoff: float,
        session: requests.Session | None = None,
    ) -> None:
        self.url = f"{base_url.rstrip('/')}/employees"
        self.timeout = (connect_timeout, read_timeout)
        self.retry_count = retry_count
        self.retry_backoff = retry_backoff
        self.session = session or requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def fetch(self) -> list[KotEmployee]:
        last_error: Exception | None = None
        for attempt in range(1, self.retry_count + 1):
            try:
                response = self.session.get(
                    self.url,
                    params={
                        "additionalFields": "emailAddresses,resignationDate",
                        "includeResigner": "true",
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list):
                    raise KotEmployeeSyncError("Unexpected KOT employee response format")
                return parse_kot_employees(payload)
            except (requests.RequestException, ValueError, KotEmployeeSyncError) as exc:
                last_error = exc
                if attempt < self.retry_count:
                    time.sleep(self.retry_backoff * attempt)
        raise KotEmployeeSyncError(f"KOT employee fetch failed: {last_error}")


def parse_kot_employees(payload: list[object]) -> list[KotEmployee]:
    result: list[KotEmployee] = []
    seen: set[str] = set()
    for raw in payload:
        if not isinstance(raw, dict):
            raise KotEmployeeSyncError("KOT employee record must be an object")
        code = str(raw.get("code", "")).strip()
        key = str(raw.get("key", "")).strip()
        last_name = str(raw.get("lastName", "")).strip()
        first_name = str(raw.get("firstName", "")).strip()
        division_code = str(raw.get("divisionCode", "")).strip()
        if not all((code, key, last_name, first_name, division_code)):
            raise KotEmployeeSyncError("KOT employee record has missing required fields")
        if code in seen:
            raise KotEmployeeSyncError(f"Duplicate KOT employee code: {code}")
        seen.add(code)
        emails = raw.get("emailAddresses")
        email = ""
        if isinstance(emails, list):
            for value in emails:
                if isinstance(value, str) and value.strip():
                    email = value.strip()
                    break
                if isinstance(value, dict):
                    candidate = str(
                        value.get(
                            "emailAddress",
                            value.get("email", value.get("value", "")),
                        )
                    ).strip()
                    if candidate:
                        email = candidate
                        break
        groups = raw.get("employeeGroups")
        group_codes: list[str] = []
        group_names: list[str] = []
        if isinstance(groups, list):
            for group in groups:
                if isinstance(group, dict):
                    group_codes.append(str(group.get("code", "")).strip())
                    group_names.append(str(group.get("name", "")).strip())
        result.append(
            KotEmployee(
                code=code,
                key=key,
                last_name=last_name,
                first_name=first_name,
                email=email,
                division_code=division_code,
                division_name=str(raw.get("divisionName", "")).strip(),
                group_codes=tuple(filter(None, group_codes)),
                group_names=tuple(filter(None, group_names)),
                resignation_date=str(raw.get("resignationDate", "") or "").strip(),
            )
        )
    return result


class KotEmployeeSyncService:
    PREVIEW_TTL_SECONDS = 900

    def __init__(
        self,
        database: Database,
        employee_csv: Path,
        client: KotEmployeeSource,
        target_division_codes: tuple[str, ...],
        backup_root: Path | None = None,
    ) -> None:
        normalized_codes = tuple(
            dict.fromkeys(code.strip() for code in target_division_codes if code.strip())
        )
        if not normalized_codes:
            raise KotEmployeeSyncError("At least one KOT sync division code is required")
        self.database = database
        self.employee_csv = employee_csv
        self.client = client
        self.target_division_codes = normalized_codes
        self.backup_root = backup_root or database.path.parent / "backups" / "kot-sync"
        self.repository = EmployeeRepository(database)
        self._previews: dict[str, _Preview] = {}
        self._lock = threading.Lock()

    def preview(self) -> tuple[str, list[SyncDifference]]:
        fetched_employees = self.client.fetch()
        target_codes = set(self.target_division_codes)
        kot_employees = [
            employee for employee in fetched_employees if employee.division_code in target_codes
        ]
        current = {
            employee.code: employee
            for employee in self.repository.list_managed()
            if employee.division_code in target_codes
        }
        with self.database.connect() as conn:
            current_keys = {
                row["code"]: row["kot_key"]
                for row in conn.execute("SELECT code, kot_key FROM employees")
            }
        remote = {employee.code: employee for employee in kot_employees}
        differences: list[SyncDifference] = []
        for code in sorted(current.keys() | remote.keys()):
            local = current.get(code)
            kot = remote.get(code)
            if kot is None and local is not None:
                action = "disable" if local.is_enabled else "unchanged"
                differences.append(SyncDifference(code, action, self._local_dict(local), None, ()))
                continue
            assert kot is not None
            warnings = tuple(self._warnings(kot))
            proposed = self._kot_dict(kot)
            if local is None:
                action = "disable" if kot.resignation_date else "create"
                differences.append(SyncDifference(code, action, None, proposed, warnings))
                continue
            changed_fields = self._changed_fields(
                local,
                kot,
                current_keys.get(code),
            )
            action = (
                "disable" if kot.resignation_date else ("update" if changed_fields else "unchanged")
            )
            differences.append(
                SyncDifference(
                    code,
                    action,
                    self._local_dict(local),
                    proposed,
                    warnings,
                    changed_fields,
                )
            )
        preview_id = secrets.token_urlsafe(24)
        with self._lock:
            self._prune()
            self._previews[preview_id] = _Preview(
                time.time(),
                remote,
                differences,
                fetched_count=len(fetched_employees),
                target_count=len(kot_employees),
            )
        return preview_id, differences

    def preview_metadata(self, preview_id: str) -> dict[str, object]:
        with self._lock:
            self._prune()
            preview = self._previews.get(preview_id)
        if preview is None:
            raise KotEmployeeSyncError("Preview expired or does not exist; fetch again")
        return {
            "fetchedCount": preview.fetched_count,
            "targetCount": preview.target_count,
            "targetDivisionCodes": list(self.target_division_codes),
        }

    def _create_apply_backup(self, now: datetime) -> Path:
        backup_name = now.strftime("%Y%m%d_%H%M%S_%f")
        backup_dir = self.backup_root / backup_name
        database_backup = backup_dir / self.database.path.name
        csv_backup = backup_dir / self.employee_csv.name

        if backup_dir.exists():
            raise KotEmployeeSyncError(f"Backup destination already exists: {backup_dir}")

        try:
            backup_dir.mkdir(parents=True, mode=0o700)
            backup_dir.chmod(0o700)
            self.database.backup_to(database_backup)
            database_backup.chmod(0o600)
            if self.employee_csv.exists():
                shutil.copy2(self.employee_csv, csv_backup)
                csv_backup.chmod(0o600)
            return backup_dir
        except Exception as exc:
            shutil.rmtree(backup_dir, ignore_errors=True)
            raise KotEmployeeSyncError(f"KOT sync backup failed: {exc}") from exc

    def apply(
        self,
        preview_id: str,
        selected_codes: list[str],
        actor: str,
        now: datetime,
    ) -> dict[str, int]:
        with self._lock:
            self._prune()
            preview = self._previews.get(preview_id)
        if preview is None:
            raise KotEmployeeSyncError("Preview expired or does not exist; fetch again")
        selected = set(selected_codes)
        allowed = {diff.code for diff in preview.differences if diff.action != "unchanged"}
        if not selected or not selected <= allowed:
            raise KotEmployeeSyncError("Select one or more valid differences")

        self._create_apply_backup(now)

        original_csv = self.employee_csv.read_bytes() if self.employee_csv.exists() else None
        csv_replaced = False
        temp_path: Path | None = None
        counts = {"created": 0, "updated": 0, "disabled": 0}
        try:
            with self.database.transaction() as conn:
                for diff in preview.differences:
                    if diff.code not in selected:
                        continue
                    kot = preview.employees.get(diff.code)
                    if diff.action == "disable":
                        reason = (
                            "KOT退職済み" if kot and kot.resignation_date else "KOTに存在しない"
                        )
                        if kot is None:
                            conn.execute(
                                """
                                UPDATE employees
                                SET
                                    is_enabled=0,
                                    disabled_reason=?,
                                    kot_exists=0,
                                    updated_at=?,
                                    last_synced_at=?
                                WHERE code=?
                                """,
                                (
                                    reason,
                                    now.isoformat(),
                                    now.isoformat(),
                                    diff.code,
                                ),
                            )
                        else:
                            conn.execute(
                                """
                                INSERT INTO employees(
                                    code,
                                    kot_key,
                                    last_name,
                                    first_name,
                                    division_code,
                                    division_name,
                                    email,
                                    personal_target_minutes,
                                    is_enabled,
                                    disabled_reason,
                                    note,
                                    kot_group_codes,
                                    kot_group_names,
                                    kot_exists,
                                    created_at,
                                    updated_at,
                                    last_synced_at
                                ) VALUES(
                                    ?, ?, ?, ?, ?, ?, ?,
                                    NULL, 0, ?, NULL, ?, ?, 1, ?, ?, ?
                                )
                                ON CONFLICT(code) DO UPDATE SET
                                    kot_key=excluded.kot_key,
                                    last_name=excluded.last_name,
                                    first_name=excluded.first_name,
                                    division_code=excluded.division_code,
                                    division_name=excluded.division_name,
                                    email=excluded.email,
                                    is_enabled=0,
                                    disabled_reason=excluded.disabled_reason,
                                    kot_group_codes=excluded.kot_group_codes,
                                    kot_group_names=excluded.kot_group_names,
                                    kot_exists=1,
                                    updated_at=excluded.updated_at,
                                    last_synced_at=excluded.last_synced_at
                                """,
                                (
                                    kot.code,
                                    kot.key,
                                    kot.last_name,
                                    kot.first_name,
                                    kot.division_code,
                                    kot.division_name,
                                    kot.email or None,
                                    reason,
                                    ",".join(kot.group_codes),
                                    ",".join(kot.group_names),
                                    now.isoformat(),
                                    now.isoformat(),
                                    now.isoformat(),
                                ),
                            )
                        counts["disabled"] += 1
                        continue
                    assert kot is not None
                    existing = conn.execute(
                        "SELECT code FROM employees WHERE code=?",
                        (kot.code,),
                    ).fetchone()
                    conn.execute(
                        """
                        INSERT INTO employees(
                            code, kot_key, last_name, first_name, division_code, division_name,
                            email, personal_target_minutes, is_enabled, disabled_reason, note,
                            kot_group_codes, kot_group_names, kot_exists, created_at, updated_at,
                            last_synced_at
                        ) VALUES(?, ?, ?, ?, ?, ?, ?, NULL, 1, NULL, NULL, ?, ?, 1, ?, ?, ?)
                        ON CONFLICT(code) DO UPDATE SET
                            kot_key=excluded.kot_key,
                            last_name=excluded.last_name,
                            first_name=excluded.first_name,
                            division_code=excluded.division_code,
                            division_name=excluded.division_name,
                            email=excluded.email,
                            is_enabled=1,
                            disabled_reason=NULL,
                            kot_group_codes=excluded.kot_group_codes,
                            kot_group_names=excluded.kot_group_names,
                            kot_exists=1,
                            updated_at=excluded.updated_at,
                            last_synced_at=excluded.last_synced_at
                        """,
                        (
                            kot.code,
                            kot.key,
                            kot.last_name,
                            kot.first_name,
                            kot.division_code,
                            kot.division_name,
                            kot.email or None,
                            ",".join(kot.group_codes),
                            ",".join(kot.group_names),
                            now.isoformat(),
                            now.isoformat(),
                            now.isoformat(),
                        ),
                    )
                    counts["updated" if existing else "created"] += 1
                enabled = self.repository.list_enabled(conn=conn)
                if not enabled:
                    raise KotEmployeeSyncError("At least one enabled employee is required")
                self.employee_csv.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    prefix=f".{self.employee_csv.name}.",
                    suffix=".tmp",
                    dir=self.employee_csv.parent,
                    delete=False,
                ) as handle:
                    temp_path = Path(handle.name)
                write_employees(temp_path, enabled)
                if len(load_employees(temp_path)) != len(enabled):
                    raise EmployeeDataError("Generated employee CSV validation failed")
                temp_path.replace(self.employee_csv)
                csv_replaced = True
                unchanged_count = sum(diff.action == "unchanged" for diff in preview.differences)
                conn.execute(
                    """
                    INSERT INTO kot_sync_runs(
                        executed_at,
                        actor,
                        fetched_count,
                        created_count,
                        updated_count,
                        disabled_count,
                        unchanged_count,
                        status,
                        error_summary
                    ) VALUES(
                        ?, ?, ?, ?, ?, ?, ?, 'succeeded', NULL
                    )
                    """,
                    (
                        now.isoformat(),
                        actor,
                        len(preview.employees),
                        counts["created"],
                        counts["updated"],
                        counts["disabled"],
                        unchanged_count,
                    ),
                )
        except Exception:
            if csv_replaced:
                if original_csv is None:
                    self.employee_csv.unlink(missing_ok=True)
                else:
                    self.employee_csv.write_bytes(original_csv)
            raise
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)
        with self._lock:
            self._previews.pop(preview_id, None)
        return counts

    def history(self, limit: int = 20) -> list[dict[str, object]]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    executed_at,
                    actor,
                    fetched_count,
                    created_count,
                    updated_count,
                    disabled_count,
                    unchanged_count,
                    status,
                    error_summary
                FROM kot_sync_runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _prune(self) -> None:
        cutoff = time.time() - self.PREVIEW_TTL_SECONDS
        self._previews = {
            key: value for key, value in self._previews.items() if value.created_at >= cutoff
        }

    @staticmethod
    def _changed_fields(
        local: ManagedEmployee,
        kot: KotEmployee,
        current_key: str | None,
    ) -> tuple[str, ...]:
        changed: list[str] = []
        comparisons = (
            ("lastName", local.last_name, kot.last_name),
            ("firstName", local.first_name, kot.first_name),
            ("email", local.email, kot.email),
            ("divisionCode", local.division_code, kot.division_code),
            ("divisionName", local.division_name, kot.division_name),
        )
        changed.extend(name for name, current, proposed in comparisons if current != proposed)
        if not local.kot_exists:
            changed.append("kotExists")
        if current_key != kot.key:
            changed.append("kotKey")
        return tuple(changed)

    @staticmethod
    def _warnings(employee: KotEmployee) -> list[str]:
        notable = {"non", "leave", "outsource", "SEC001"}
        return [
            name
            for code, name in zip(
                employee.group_codes,
                employee.group_names,
                strict=False,
            )
            if code in notable
        ]

    @staticmethod
    def _local_dict(employee: ManagedEmployee) -> dict[str, object]:
        return {
            "lastName": employee.last_name,
            "firstName": employee.first_name,
            "email": employee.email,
            "divisionCode": employee.division_code,
            "divisionName": employee.division_name,
            "isEnabled": employee.is_enabled,
        }

    @staticmethod
    def _kot_dict(employee: KotEmployee) -> dict[str, object]:
        return {
            "lastName": employee.last_name,
            "firstName": employee.first_name,
            "email": employee.email,
            "divisionCode": employee.division_code,
            "divisionName": employee.division_name,
            "isEnabled": not bool(employee.resignation_date),
        }
