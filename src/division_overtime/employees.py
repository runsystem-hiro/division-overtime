from __future__ import annotations

import csv
import logging
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from .models import Employee

logger = logging.getLogger(__name__)

EMPLOYEE_CSV_BACKUP_RETENTION = 30


class EmployeeDataError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EmployeeCsvGenerationResult:
    status: Literal["success"]
    generated_at: datetime
    employee_count: int
    output_path: Path
    backup_path: Path | None
    removed_backup_count: int


def _optional_non_negative_int(value: str | None, employee_code: str) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise EmployeeDataError(
            f"Invalid personal overtime target for employee {employee_code}: {value!r}"
        ) from exc
    if parsed < 0:
        raise EmployeeDataError(
            f"Personal overtime target must be >= 0 for employee {employee_code}"
        )
    return parsed


def load_employees(path: Path) -> list[Employee]:
    if not path.exists():
        raise EmployeeDataError(f"Employee CSV not found: {path}")
    employees: list[Employee] = []
    seen_codes: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"社員番号", "キー", "氏", "名", "メールアドレス", "部署コード"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise EmployeeDataError(f"Missing CSV columns: {', '.join(sorted(missing))}")
        for row_number, row in enumerate(reader, start=2):
            code = row["社員番号"].strip()
            if not code:
                raise EmployeeDataError(f"Empty employee code at row {row_number}")
            if code in seen_codes:
                raise EmployeeDataError(f"Duplicate employee code: {code}")
            seen_codes.add(code)
            employees.append(
                Employee(
                    code=code,
                    employee_key=row["キー"].strip(),
                    last_name=row["氏"].strip(),
                    first_name=row["名"].strip(),
                    email=row["メールアドレス"].strip(),
                    division_code=row["部署コード"].strip(),
                    division_name=(row.get("部署名") or "").strip(),
                    personal_target_minutes=_optional_non_negative_int(
                        row.get("個人別残業上限分"), code
                    ),
                )
            )
    return employees


CSV_FIELDNAMES = [
    "社員番号",
    "キー",
    "氏",
    "名",
    "メールアドレス",
    "部署コード",
    "部署名",
    "個人別残業上限分",
]


def write_employees(path: Path, employees: list[Employee]) -> None:
    if not employees:
        raise EmployeeDataError("Cannot write an empty employee CSV")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for employee in employees:
            required_values = {
                "社員番号": employee.code,
                "キー": employee.employee_key,
                "氏": employee.last_name,
                "名": employee.first_name,
                "部署コード": employee.division_code,
            }
            missing = [name for name, value in required_values.items() if not value.strip()]
            if missing:
                raise EmployeeDataError(
                    f"Employee {employee.code or '<unknown>'} has empty required fields: "
                    + ", ".join(missing)
                )
            writer.writerow(
                {
                    **required_values,
                    "メールアドレス": employee.email,
                    "部署名": employee.division_name,
                    "個人別残業上限分": (
                        ""
                        if employee.personal_target_minutes is None
                        else employee.personal_target_minutes
                    ),
                }
            )


def _prune_employee_csv_backups(
    backup_dir: Path, source_path: Path, retention: int = EMPLOYEE_CSV_BACKUP_RETENTION
) -> int:
    if retention < 1:
        raise ValueError("Employee CSV backup retention must be at least 1")
    pattern = re.compile(
        rf"^{re.escape(source_path.stem)}_\d{{8}}_\d{{12}}{re.escape(source_path.suffix)}$"
    )
    backups = sorted(
        candidate
        for candidate in backup_dir.iterdir()
        if candidate.is_file() and pattern.fullmatch(candidate.name)
    )
    expired = backups[:-retention]
    for backup in expired:
        backup.unlink()
    return len(expired)


def generate_employee_csv(
    path: Path, employees: list[Employee], *, generated_at: datetime | None = None
) -> EmployeeCsvGenerationResult:
    """Validate and atomically replace the legacy employee CSV."""
    generated_at = generated_at or datetime.now().astimezone()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    backup_path: Path | None = None
    removed_backup_count = 0
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)

        write_employees(temp_path, employees)
        validated = load_employees(temp_path)
        if len(validated) != len(employees):
            raise EmployeeDataError("Generated employee CSV validation count mismatch")

        if path.exists():
            backup_dir = path.parent / "backups" / "employee-csv"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_dir.chmod(0o700)
            timestamp = generated_at.strftime("%Y%m%d_%H%M%S%f")
            backup_path = backup_dir / f"{path.stem}_{timestamp}{path.suffix}"
            shutil.copy2(path, backup_path)
            backup_path.chmod(0o600)

        temp_path.replace(path)
        if backup_path is not None:
            try:
                removed_backup_count = _prune_employee_csv_backups(backup_path.parent, path)
            except Exception:
                logger.warning(
                    "employee_csv_backup_prune=failed backup_dir=%s retention=%d",
                    backup_path.parent,
                    EMPLOYEE_CSV_BACKUP_RETENTION,
                    exc_info=True,
                )
    except Exception:
        logger.exception("employee_csv_generation=failed output_path=%s", path)
        raise
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    result = EmployeeCsvGenerationResult(
        status="success",
        generated_at=generated_at,
        employee_count=len(employees),
        output_path=path,
        backup_path=backup_path,
        removed_backup_count=removed_backup_count,
    )
    logger.info(
        "employee_csv_generation=success generated_at=%s employees=%d output_path=%s "
        "backup_path=%s removed_backups=%d",
        result.generated_at.isoformat(),
        result.employee_count,
        result.output_path,
        result.backup_path,
        result.removed_backup_count,
    )
    return result
