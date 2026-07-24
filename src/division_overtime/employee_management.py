from __future__ import annotations

import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .database import Database
from .employee_repository import EmployeeRepository, ManagedEmployee
from .employees import EmployeeDataError, load_employees, write_employees


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
        if not (change.employee_key or "").strip():
            raise EmployeeManagementError("KOT key is required when creating an employee.")
        return self._save(change, updated_at, create=True)

    def update_employee(
        self, code: str, change: EmployeeChange, updated_at: datetime
    ) -> ManagedEmployee:
        if code != change.code:
            raise EmployeeManagementError("Employee code cannot be changed.")
        return self._save(change, updated_at, create=False)

    def _save(
        self, change: EmployeeChange, updated_at: datetime, *, create: bool
    ) -> ManagedEmployee:
        self._validate(change)
        with self._write_lock:
            original_csv = self.employee_csv.read_bytes() if self.employee_csv.exists() else None
            csv_replaced = False
            temp_path: Path | None = None
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

                    with tempfile.NamedTemporaryFile(
                        mode="wb",
                        prefix=f".{self.employee_csv.name}.",
                        suffix=".tmp",
                        dir=self.employee_csv.parent,
                        delete=False,
                    ) as handle:
                        temp_path = Path(handle.name)

                    write_employees(temp_path, enabled_employees)
                    validated = load_employees(temp_path)
                    if len(validated) != len(enabled_employees):
                        raise EmployeeDataError("Generated employee CSV validation failed")
                    temp_path.replace(self.employee_csv)
                    csv_replaced = True

                saved = self.repository.get_managed(change.code)
                if saved is None:
                    raise EmployeeManagementError("Saved employee could not be reloaded.")
                return saved
            except Exception:
                if csv_replaced:
                    if original_csv is None:
                        self.employee_csv.unlink(missing_ok=True)
                    else:
                        self.employee_csv.write_bytes(original_csv)
                raise
            finally:
                if temp_path is not None:
                    temp_path.unlink(missing_ok=True)

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
