from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .database import Database
from .employees import load_employees
from .models import Employee

if TYPE_CHECKING:
    from .employee_management import EmployeeChange


@dataclass(frozen=True, slots=True)
class ManagedEmployee:
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
    kot_exists: bool
    created_at: str
    updated_at: str

    @property
    def full_name(self) -> str:
        return f"{self.last_name}{self.first_name}"


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

    def list_enabled(self, *, conn: sqlite3.Connection | None = None) -> list[Employee]:
        owns_connection = conn is None
        active_conn = conn or self.database.connect()
        try:
            rows = active_conn.execute(
                """
                SELECT
                    code,
                    kot_key,
                    last_name,
                    first_name,
                    email,
                    division_code,
                    division_name,
                    personal_target_minutes
                FROM employees
                WHERE is_enabled=1
                ORDER BY code
                """
            ).fetchall()
        finally:
            if owns_connection:
                active_conn.close()
        return [
            Employee(
                code=row["code"],
                employee_key=row["kot_key"],
                last_name=row["last_name"],
                first_name=row["first_name"],
                email=row["email"] or "",
                division_code=row["division_code"],
                division_name=row["division_name"],
                personal_target_minutes=row["personal_target_minutes"],
            )
            for row in rows
        ]

    def list_managed(
        self, *, query: str = "", enabled: bool | None = None
    ) -> list[ManagedEmployee]:
        clauses: list[str] = []
        parameters: list[object] = []
        normalized = query.strip()
        if normalized:
            clauses.append(
                "(code LIKE ? OR last_name LIKE ? OR first_name LIKE ? "
                "OR division_code LIKE ? OR division_name LIKE ?)"
            )
            pattern = f"%{normalized}%"
            parameters.extend([pattern] * 5)
        if enabled is not None:
            clauses.append("is_enabled=?")
            parameters.append(int(enabled))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.database.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    code, last_name, first_name, email, division_code, division_name,
                    personal_target_minutes, is_enabled, disabled_reason, note,
                    kot_exists, created_at, updated_at
                FROM employees
                {where}
                ORDER BY code
                """,
                parameters,
            ).fetchall()
        return [self._to_managed(row) for row in rows]

    def get_managed(
        self, code: str, *, conn: sqlite3.Connection | None = None
    ) -> ManagedEmployee | None:
        owns_connection = conn is None
        active_conn = conn or self.database.connect()
        try:
            row = active_conn.execute(
                """
                SELECT
                    code, last_name, first_name, email, division_code, division_name,
                    personal_target_minutes, is_enabled, disabled_reason, note,
                    kot_exists, created_at, updated_at
                FROM employees
                WHERE code=?
                """,
                (code,),
            ).fetchone()
        finally:
            if owns_connection:
                active_conn.close()
        return None if row is None else self._to_managed(row)

    def save_managed(
        self,
        change: EmployeeChange,
        *,
        updated_at: datetime,
        create: bool,
        conn: sqlite3.Connection,
    ) -> None:
        timestamp = updated_at.isoformat()
        email = change.email.strip() or None
        disabled_reason = change.disabled_reason.strip() or None
        note = change.note.strip() or None
        if create:
            conn.execute(
                """
                INSERT INTO employees(
                    code, kot_key, last_name, first_name, division_code, division_name,
                    email, personal_target_minutes, is_enabled, disabled_reason, note,
                    kot_exists, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    change.code.strip(),
                    (change.employee_key or "").strip(),
                    change.last_name.strip(),
                    change.first_name.strip(),
                    change.division_code.strip(),
                    change.division_name.strip(),
                    email,
                    change.personal_target_minutes,
                    int(change.is_enabled),
                    disabled_reason,
                    note,
                    timestamp,
                    timestamp,
                ),
            )
            return

        if change.employee_key and change.employee_key.strip():
            key_sql = "kot_key=? ,"
            parameters: list[object] = [change.employee_key.strip()]
        else:
            key_sql = ""
            parameters = []
        parameters.extend(
            [
                change.last_name.strip(),
                change.first_name.strip(),
                change.division_code.strip(),
                change.division_name.strip(),
                email,
                change.personal_target_minutes,
                int(change.is_enabled),
                disabled_reason,
                note,
                timestamp,
                change.code,
            ]
        )
        cursor = conn.execute(
            f"""
            UPDATE employees SET
                {key_sql}
                last_name=?, first_name=?, division_code=?, division_name=?,
                email=?, personal_target_minutes=?, is_enabled=?, disabled_reason=?,
                note=?, updated_at=?
            WHERE code=?
            """,
            parameters,
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"Employee not found: {change.code}")

    def count(self) -> int:
        with self.database.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0])

    @staticmethod
    def _to_managed(row: sqlite3.Row) -> ManagedEmployee:
        return ManagedEmployee(
            code=row["code"],
            last_name=row["last_name"],
            first_name=row["first_name"],
            email=row["email"] or "",
            division_code=row["division_code"],
            division_name=row["division_name"],
            personal_target_minutes=row["personal_target_minutes"],
            is_enabled=bool(row["is_enabled"]),
            disabled_reason=row["disabled_reason"] or "",
            note=row["note"] or "",
            kot_exists=bool(row["kot_exists"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
