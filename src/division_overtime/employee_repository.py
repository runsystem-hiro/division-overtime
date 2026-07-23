from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .database import Database
from .employees import load_employees
from .models import Employee


class EmployeeRepository:
    def __init__(self, database: Database):
        self.database = database

    def import_csv(self, path: Path, imported_at: datetime) -> int:
        employees = load_employees(path)
        self.upsert_many(employees, imported_at)
        return len(employees)

    def upsert_many(self, employees: list[Employee], updated_at: datetime) -> None:
        timestamp = updated_at.isoformat()
        values = [
            (
                employee.code,
                employee.employee_key,
                employee.last_name,
                employee.first_name,
                employee.division_code,
                employee.division_name,
                employee.email or None,
                employee.personal_target_minutes,
                timestamp,
                timestamp,
            )
            for employee in employees
        ]
        with self.database.transaction() as conn:
            conn.executemany(
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
                    created_at,
                    updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    kot_key=excluded.kot_key,
                    last_name=excluded.last_name,
                    first_name=excluded.first_name,
                    division_code=excluded.division_code,
                    division_name=excluded.division_name,
                    email=excluded.email,
                    personal_target_minutes=excluded.personal_target_minutes,
                    kot_exists=1,
                    updated_at=excluded.updated_at
                """,
                values,
            )

    def count(self) -> int:
        with self.database.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0])
