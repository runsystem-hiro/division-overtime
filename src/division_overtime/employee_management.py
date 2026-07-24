from __future__ import annotations

import shutil
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .database import Database
from .employee_repository import EmployeeRepository, ManagedEmployee
from .employees import EmployeeCsvGenerationResult, generate_employee_csv, load_employees


class EmployeeManagementError(RuntimeError):
    """Raised when an employee management operation cannot be completed safely."""


class EmployeeNotFoundError(EmployeeManagementError):
    pass


class EmployeeConflictError(EmployeeManagementError):
    pass


@dataclass(frozen=True, slots=True)
class EmployeeChange:
    code: str
    last_name: str
    first_name: str
    email: str
    division_code: str
    division_name: str
    personal_target_minutes: int | None
    is_enabled: bool
    disabled_reason: str
    note: str
    employee_key: str | None = None


@dataclass(frozen=True, slots=True)
class EmployeeSaveResult:
    employee: ManagedEmployee
    csv: EmployeeCsvGenerationResult


@dataclass(frozen=True, slots=True)
class EmployeeDeleteResult:
    employee: ManagedEmployee
    csv: EmployeeCsvGenerationResult
    backup_path: Path


class EmployeeManagementService:
    """Keep SQLite employee data and the legacy employee CSV synchronized."""

    def __init__(self, database: Database, employee_csv: Path):
        self.database = database
        self.employee_csv = employee_csv
        self.repository = EmployeeRepository(database)
        self._write_lock = threading.Lock()

    def list_employees(
        self, *, query: str = "", enabled: bool | None = None
    ) -> list[ManagedEmployee]:
        return self.repository.list_managed(query=query, enabled=enabled)

    def get_employee(self, code: str) -> ManagedEmployee:
        employee = self.repository.get_managed(code)
        if employee is None:
            raise EmployeeNotFoundError(f"Employee not found: {code}")
        return employee

    def create_employee(self, change: EmployeeChange, updated_at: datetime) -> ManagedEmployee:
        return self.create_employee_with_result(change, updated_at).employee

    def create_employee_with_result(
        self, change: EmployeeChange, updated_at: datetime
    ) -> EmployeeSaveResult:
        if not (change.employee_key or "").strip():
            raise EmployeeManagementError("KOT key is required when creating an employee.")
        return self._save(change, updated_at, create=True)

    def update_employee(
        self, code: str, change: EmployeeChange, updated_at: datetime
    ) -> ManagedEmployee:
        return self.update_employee_with_result(code, change, updated_at).employee

    def update_employee_with_result(
        self, code: str, change: EmployeeChange, updated_at: datetime
    ) -> EmployeeSaveResult:
        if code != change.code:
            raise EmployeeManagementError("Employee code cannot be changed.")
        return self._save(change, updated_at, create=False)

    def delete_employee_with_result(self, code: str, deleted_at: datetime) -> EmployeeDeleteResult:
        with self._write_lock:
            employee = self.repository.get_managed(code)
            if employee is None:
                raise EmployeeNotFoundError(f"Employee not found: {code}")

            backup_path = self._create_delete_backup(deleted_at)
            original_csv = self.employee_csv.read_bytes() if self.employee_csv.exists() else None
            csv_replaced = False
            try:
                with self.database.transaction() as conn:
                    self.repository.delete_managed(code, conn=conn)
                    enabled_employees = self.repository.list_enabled(conn=conn)
                    if not enabled_employees:
                        raise EmployeeManagementError(
                            "At least one enabled employee is required; "
                            "employee CSV was not changed."
                        )
                    csv_result = generate_employee_csv(
                        self.employee_csv, enabled_employees, generated_at=deleted_at
                    )
                    csv_replaced = True
                return EmployeeDeleteResult(
                    employee=employee, csv=csv_result, backup_path=backup_path
                )
            except Exception:
                if csv_replaced:
                    if original_csv is None:
                        self.employee_csv.unlink(missing_ok=True)
                    else:
                        self.employee_csv.write_bytes(original_csv)
                raise

    def _create_delete_backup(self, deleted_at: datetime) -> Path:
        backup_root = self.database.path.parent / "backups" / "employee-delete"
        backup_path = backup_root / deleted_at.strftime("%Y%m%d_%H%M%S_%f")
        if backup_path.exists():
            raise EmployeeManagementError(f"Backup destination already exists: {backup_path}")
        try:
            backup_path.mkdir(parents=True, mode=0o700)
            backup_path.chmod(0o700)
            database_backup = backup_path / self.database.path.name
            self.database.backup_to(database_backup)
            database_backup.chmod(0o600)
            if self.employee_csv.exists():
                csv_backup = backup_path / self.employee_csv.name
                shutil.copy2(self.employee_csv, csv_backup)
                csv_backup.chmod(0o600)
            return backup_path
        except Exception as exc:
            shutil.rmtree(backup_path, ignore_errors=True)
            raise EmployeeManagementError(f"Employee delete backup failed: {exc}") from exc

    def _save(
        self, change: EmployeeChange, updated_at: datetime, *, create: bool
    ) -> EmployeeSaveResult:
        self._validate(change)
        with self._write_lock:
            original_csv = self.employee_csv.read_bytes() if self.employee_csv.exists() else None
            csv_replaced = False
            self.employee_csv.parent.mkdir(parents=True, exist_ok=True)
            try:
                with self.database.transaction() as conn:
                    existing = self.repository.get_managed(change.code, conn=conn)
                    if create and existing is not None:
                        raise EmployeeConflictError(f"Employee code already exists: {change.code}")
                    if not create and existing is None:
                        raise EmployeeNotFoundError(f"Employee not found: {change.code}")

                    self.repository.save_managed(
                        change,
                        updated_at=updated_at,
                        create=create,
                        conn=conn,
                    )
                    enabled_employees = self.repository.list_enabled(conn=conn)
                    if not enabled_employees:
                        raise EmployeeManagementError(
                            "At least one enabled employee is required; "
                            "employee CSV was not changed."
                        )

                    csv_result = generate_employee_csv(
                        self.employee_csv, enabled_employees, generated_at=updated_at
                    )
                    csv_replaced = True

                saved = self.repository.get_managed(change.code)
                if saved is None:
                    raise EmployeeManagementError("Saved employee could not be reloaded.")
                return EmployeeSaveResult(employee=saved, csv=csv_result)
            except Exception:
                if csv_replaced:
                    if original_csv is None:
                        self.employee_csv.unlink(missing_ok=True)
                    else:
                        self.employee_csv.write_bytes(original_csv)
                raise

    def get_csv_employee_count(self) -> int:
        """Return the number of employees currently written to the legacy CSV."""
        return len(load_employees(self.employee_csv))

    @staticmethod
    def _validate(change: EmployeeChange) -> None:
        required = {
            "employee code": change.code,
            "last name": change.last_name,
            "first name": change.first_name,
            "division code": change.division_code,
        }
        missing = [label for label, value in required.items() if not value.strip()]
        if missing:
            raise EmployeeManagementError("Required fields are empty: " + ", ".join(missing))
        if change.personal_target_minutes is not None and change.personal_target_minutes < 0:
            raise EmployeeManagementError("Personal overtime target must be 0 or greater.")
        if not change.is_enabled and not change.disabled_reason.strip():
            raise EmployeeManagementError("Disabled reason is required when disabling an employee.")
