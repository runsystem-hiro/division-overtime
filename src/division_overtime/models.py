from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Employee:
    code: str
    employee_key: str
    last_name: str
    first_name: str
    email: str
    division_code: str
    division_name: str = ""
    personal_target_minutes: int | None = None

    @property
    def full_name(self) -> str:
        return f"{self.last_name}{self.first_name}"


@dataclass(frozen=True, slots=True)
class OvertimeSnapshot:
    employee: Employee
    target_month: str
    current_minutes: int
    previous_minutes: int
    target_minutes: int

    @property
    def target_percent(self) -> int:
        if self.target_minutes == 0:
            return 100 if self.current_minutes > 0 else 0
        return round(self.current_minutes / self.target_minutes * 100)

    @property
    def previous_percent(self) -> int:
        if self.previous_minutes == 0:
            return 0
        return round(self.current_minutes / self.previous_minutes * 100)
