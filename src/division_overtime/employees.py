from __future__ import annotations

import csv
import logging
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from .models import Employee

logger = logging.getLogger(__name__)


class EmployeeDataError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EmployeeCsvGenerationResult:
    status: Literal["success"]
    generated_at: datetime
    employee_count: int
    output_path: Path


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


def generate_employee_csv(
    path: Path, employees: list[Employee], *, generated_at: datetime | None = None
) -> EmployeeCsvGenerationResult:
    """Validate and atomically replace the legacy employee CSV."""
    generated_at = generated_at or datetime.now().astimezone()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
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
        temp_path.replace(path)
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
    )
    logger.info(
        "employee_csv_generation=success generated_at=%s employees=%d output_path=%s",
        result.generated_at.isoformat(),
        result.employee_count,
        result.output_path,
    )
    return result
