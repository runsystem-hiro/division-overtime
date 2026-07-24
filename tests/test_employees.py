from pathlib import Path

import pytest

from division_overtime.employees import EmployeeDataError, load_employees
from division_overtime.models import Employee


def test_load_employee_csv(tmp_path: Path):
    path = tmp_path / "employee.csv"
    path.write_text(
        "社員番号,キー,氏,名,メールアドレス,部署コード,部署名,個人別残業上限分\n"
        "00001,key,田中,太郎,t@example.com,300,営業部,1200\n",
        encoding="utf-8",
    )
    employees = load_employees(path)
    assert employees[0].code == "00001"
    assert employees[0].personal_target_minutes == 1200


def test_csv_employee_source_matches_existing_loader(tmp_path: Path):
    from division_overtime.employee_source import CsvEmployeeSource

    path = tmp_path / "employee.csv"
    path.write_text(
        "社員番号,キー,氏,名,メールアドレス,部署コード,部署名,個人別残業上限分\n"
        "00002,key-2,佐藤,次郎,s@example.com,400,開発部,\n"
        "00001,key-1,田中,太郎,t@example.com,300,営業部,1200\n",
        encoding="utf-8",
    )

    assert CsvEmployeeSource(path).list_employees() == load_employees(path)


def test_generate_employee_csv_records_result_and_replaces_atomically(tmp_path):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from division_overtime.employees import generate_employee_csv

    path = tmp_path / "employeeKey.csv"
    path.write_text("existing", encoding="utf-8")
    generated_at = datetime(2026, 7, 24, 10, 30, tzinfo=ZoneInfo("Asia/Tokyo"))
    employees = [
        Employee(
            code="00001",
            employee_key="secret",
            last_name="田中",
            first_name="太郎",
            email="a@example.com",
            division_code="300",
            division_name="営業部",
        )
    ]

    result = generate_employee_csv(path, employees, generated_at=generated_at)

    assert result.status == "success"
    assert result.generated_at == generated_at
    assert result.employee_count == 1
    assert result.output_path == path
    assert load_employees(path)[0].code == "00001"
    assert list(tmp_path.glob(".employeeKey.csv.*.tmp")) == []


def test_generate_employee_csv_failure_preserves_existing_csv(tmp_path):
    from division_overtime.employees import generate_employee_csv

    path = tmp_path / "employeeKey.csv"
    path.write_text("existing", encoding="utf-8")
    invalid = [
        Employee(
            code="00001",
            employee_key="",
            last_name="田中",
            first_name="太郎",
            email="",
            division_code="300",
            division_name="営業部",
        )
    ]

    with pytest.raises(EmployeeDataError, match="empty required fields"):
        generate_employee_csv(path, invalid)

    assert path.read_text(encoding="utf-8") == "existing"
    assert list(tmp_path.glob(".employeeKey.csv.*.tmp")) == []
