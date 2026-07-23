from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from division_overtime.database import Database
from division_overtime.employee_management import (
    EmployeeChange,
    EmployeeManagementError,
    EmployeeManagementService,
)
from division_overtime.employee_repository import EmployeeRepository
from division_overtime.employees import load_employees
from division_overtime.models import Employee

NOW = datetime(2026, 7, 23, 11, 0, tzinfo=ZoneInfo("Asia/Tokyo"))


def _service(tmp_path):
    db = Database(tmp_path / "overtime.db")
    db.initialize()
    repository = EmployeeRepository(db)
    repository.upsert_many(
        [Employee("00001", "key-1", "田中", "太郎", "a@example.com", "300")],
        NOW,
    )
    csv_path = tmp_path / "employeeKey.csv"
    csv_path.write_text(
        "社員番号,キー,氏,名,メールアドレス,部署コード,部署名,個人別残業上限分\n"
        "00001,key-1,田中,太郎,a@example.com,300,,\n",
        encoding="utf-8",
    )
    return db, EmployeeManagementService(db, csv_path), csv_path


def test_create_employee_updates_database_and_csv(tmp_path):
    db, service, csv_path = _service(tmp_path)

    saved = service.create_employee(
        EmployeeChange(
            code="00002",
            employee_key="key-2",
            last_name="佐藤",
            first_name="花子",
            email="b@example.com",
            division_code="301",
            division_name="開発部",
            personal_target_minutes=1200,
            is_enabled=True,
            disabled_reason="",
            note="",
        ),
        NOW,
    )

    assert saved.code == "00002"
    assert EmployeeRepository(db).count() == 2
    assert [employee.code for employee in load_employees(csv_path)] == ["00001", "00002"]


def test_update_failure_rolls_back_database_and_preserves_csv(tmp_path, monkeypatch):
    db, service, csv_path = _service(tmp_path)
    original_csv = csv_path.read_bytes()

    def fail_write(*_args, **_kwargs):
        raise OSError("simulated CSV failure")

    monkeypatch.setattr("division_overtime.employee_management.write_employees", fail_write)

    with pytest.raises(OSError, match="simulated CSV failure"):
        service.update_employee(
            "00001",
            EmployeeChange(
                code="00001",
                employee_key=None,
                last_name="変更後",
                first_name="太郎",
                email="a@example.com",
                division_code="300",
                division_name="",
                personal_target_minutes=None,
                is_enabled=True,
                disabled_reason="",
                note="",
            ),
            NOW,
        )

    assert service.get_employee("00001").last_name == "田中"
    assert csv_path.read_bytes() == original_csv


def test_cannot_disable_last_enabled_employee(tmp_path):
    _, service, csv_path = _service(tmp_path)
    original_csv = csv_path.read_bytes()

    with pytest.raises(EmployeeManagementError, match="At least one enabled"):
        service.update_employee(
            "00001",
            EmployeeChange(
                code="00001",
                employee_key=None,
                last_name="田中",
                first_name="太郎",
                email="a@example.com",
                division_code="300",
                division_name="",
                personal_target_minutes=None,
                is_enabled=False,
                disabled_reason="退職",
                note="",
            ),
            NOW,
        )

    assert service.get_employee("00001").is_enabled is True
    assert csv_path.read_bytes() == original_csv
