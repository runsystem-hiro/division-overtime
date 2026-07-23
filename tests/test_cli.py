from pathlib import Path

import pytest

from division_overtime.cli import _import_employees
from division_overtime.database import Database


@pytest.fixture
def employee_csv(tmp_path: Path) -> Path:
    path = tmp_path / "employeeKey.csv"
    path.write_text(
        "社員番号,キー,氏,名,メールアドレス,部署コード,部署名,個人別残業上限分\n"
        "00001,key,田中,太郎,t@example.com,300,営業部,1200\n",
        encoding="utf-8",
    )
    return path


def test_employee_csv_import_preview_does_not_create_database(
    tmp_path: Path, employee_csv: Path, capsys
):
    db = Database(tmp_path / "test.sqlite3")

    result = _import_employees(db, employee_csv, apply=False)

    assert result == 0
    assert db.path.exists() is False
    assert capsys.readouterr().out == (
        "employee_csv_import=preview employees=1\ndatabase_changes=none\n"
    )


def test_employee_csv_import_apply_requires_initialized_database(
    tmp_path: Path, employee_csv: Path
):
    db = Database(tmp_path / "test.sqlite3")

    with pytest.raises(RuntimeError, match="Database is not initialized"):
        _import_employees(db, employee_csv, apply=True)


def test_employee_csv_import_apply_upserts_employees(tmp_path: Path, employee_csv: Path, capsys):
    db = Database(tmp_path / "test.sqlite3")
    db.initialize()

    result = _import_employees(db, employee_csv, apply=True)

    assert result == 0
    with db.connect() as conn:
        row = conn.execute(
            "SELECT code, last_name, first_name, personal_target_minutes FROM employees"
        ).fetchone()
    assert dict(row) == {
        "code": "00001",
        "last_name": "田中",
        "first_name": "太郎",
        "personal_target_minutes": 1200,
    }
    assert capsys.readouterr().out == "employee_csv_import=applied employees=1\n"
