from __future__ import annotations

import logging
from dataclasses import dataclass

from .employee_source import EmployeeSource
from .models import Employee

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EmployeeShadowDiff:
    csv_only_codes: tuple[str, ...]
    sqlite_only_codes: tuple[str, ...]
    changed_codes: tuple[str, ...]
    csv_count: int
    sqlite_count: int

    @property
    def matches(self) -> bool:
        return not (self.csv_only_codes or self.sqlite_only_codes or self.changed_codes)


def compare_employee_lists(
    csv_employees: list[Employee], sqlite_employees: list[Employee]
) -> EmployeeShadowDiff:
    csv_by_code = {employee.code: employee for employee in csv_employees}
    sqlite_by_code = {employee.code: employee for employee in sqlite_employees}
    shared_codes = csv_by_code.keys() & sqlite_by_code.keys()
    return EmployeeShadowDiff(
        csv_only_codes=tuple(sorted(csv_by_code.keys() - sqlite_by_code.keys())),
        sqlite_only_codes=tuple(sorted(sqlite_by_code.keys() - csv_by_code.keys())),
        changed_codes=tuple(
            sorted(code for code in shared_codes if csv_by_code[code] != sqlite_by_code[code])
        ),
        csv_count=len(csv_employees),
        sqlite_count=len(sqlite_employees),
    )


def log_employee_shadow_read(csv_employees: list[Employee], sqlite_source: EmployeeSource) -> None:
    try:
        diff = compare_employee_lists(csv_employees, sqlite_source.list_employees())
    except Exception as exc:
        logger.warning(
            "employee_shadow_read=failed error_type=%s",
            type(exc).__name__,
        )
        return

    if diff.matches:
        logger.info(
            "employee_shadow_read=ok csv_employees=%d sqlite_employees=%d",
            diff.csv_count,
            diff.sqlite_count,
        )
        return

    logger.warning(
        "employee_shadow_read=mismatch csv_employees=%d sqlite_employees=%d "
        "csv_only=%s sqlite_only=%s changed=%s",
        diff.csv_count,
        diff.sqlite_count,
        ",".join(diff.csv_only_codes) or "-",
        ",".join(diff.sqlite_only_codes) or "-",
        ",".join(diff.changed_codes) or "-",
    )
