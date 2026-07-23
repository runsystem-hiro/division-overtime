from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .database import Database
from .employee_repository import EmployeeRepository
from .employees import load_employees
from .models import Employee

COMPARISON_FIELDS = (
    "employee_key",
    "last_name",
    "first_name",
    "email",
    "division_code",
    "division_name",
    "personal_target_minutes",
)

DISPLAY_FIELD_NAMES = {
    "employee_key": "kot_key",
    "last_name": "last_name",
    "first_name": "first_name",
    "email": "email",
    "division_code": "division_code",
    "division_name": "division_name",
    "personal_target_minutes": "personal_target_minutes",
}


@dataclass(frozen=True, slots=True)
class EmployeeFieldDifference:
    code: str
    fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EmployeeConsistencyResult:
    database_count: int
    csv_count: int
    database_only_codes: tuple[str, ...]
    csv_only_codes: tuple[str, ...]
    field_differences: tuple[EmployeeFieldDifference, ...]

    @property
    def is_consistent(self) -> bool:
        return not (self.database_only_codes or self.csv_only_codes or self.field_differences)


def compare_employee_data(
    database_employees: list[Employee], csv_employees: list[Employee]
) -> EmployeeConsistencyResult:
    database_by_code = {employee.code: employee for employee in database_employees}
    csv_by_code = {employee.code: employee for employee in csv_employees}

    database_codes = set(database_by_code)
    csv_codes = set(csv_by_code)
    common_codes = sorted(database_codes & csv_codes)

    differences: list[EmployeeFieldDifference] = []
    for code in common_codes:
        database_employee = database_by_code[code]
        csv_employee = csv_by_code[code]
        changed_fields = tuple(
            DISPLAY_FIELD_NAMES[field]
            for field in COMPARISON_FIELDS
            if getattr(database_employee, field) != getattr(csv_employee, field)
        )
        if changed_fields:
            differences.append(EmployeeFieldDifference(code=code, fields=changed_fields))

    return EmployeeConsistencyResult(
        database_count=len(database_employees),
        csv_count=len(csv_employees),
        database_only_codes=tuple(sorted(database_codes - csv_codes)),
        csv_only_codes=tuple(sorted(csv_codes - database_codes)),
        field_differences=tuple(differences),
    )


def check_employee_data_consistency(
    database: Database, employee_csv: Path
) -> EmployeeConsistencyResult:
    if not database.is_initialized_readonly():
        raise RuntimeError(
            "Database is not initialized. Run 'division-overtime --root . database init' first."
        )
    with database.connect_readonly() as conn:
        database_employees = EmployeeRepository(database).list_enabled(conn=conn)
    csv_employees = load_employees(employee_csv)
    return compare_employee_data(database_employees, csv_employees)
