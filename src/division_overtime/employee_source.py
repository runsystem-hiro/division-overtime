from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .employee_repository import EmployeeRepository
from .employees import load_employees
from .models import Employee


class EmployeeSource(Protocol):
    """Source used by notification processing to load employees."""

    def list_employees(self) -> list[Employee]: ...


@dataclass(frozen=True, slots=True)
class CsvEmployeeSource:
    """Load notification employees from the existing employee CSV."""

    path: Path

    def list_employees(self) -> list[Employee]:
        return load_employees(self.path)


@dataclass(frozen=True, slots=True)
class SqliteEmployeeSource:
    """Load notification employees from the employee database."""

    repository: EmployeeRepository

    def list_employees(self) -> list[Employee]:
        return self.repository.list_enabled()
