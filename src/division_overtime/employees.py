from __future__ import annotations

import csv
from pathlib import Path

from .models import Employee


class EmployeeDataError(RuntimeError):
    pass


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
