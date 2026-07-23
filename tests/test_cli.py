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


def _seed_employee(db: Database, *, enabled: bool = True) -> None:
    db.initialize()
    with db.transaction() as conn:
        conn.execute(
            """
            INSERT INTO employees(
                code, kot_key, last_name, first_name, division_code,
                division_name, email, personal_target_minutes,
                is_enabled, created_at, updated_at
            )
            VALUES('00001', 'key', '田中', '太郎', '300',
                   '営業部', 't@example.com', 1200, ?, 'now', 'now')
            """,
            (int(enabled),),
        )


def test_employee_csv_export_preview_does_not_change_csv(tmp_path: Path, capsys):
    from division_overtime.cli import _export_employees

    db = Database(tmp_path / "test.sqlite3")
    _seed_employee(db)
    csv_path = tmp_path / "employeeKey.csv"
    csv_path.write_text("existing", encoding="utf-8")

    result = _export_employees(db, csv_path, apply=False)

    assert result == 0
    assert csv_path.read_text(encoding="utf-8") == "existing"
    assert capsys.readouterr().out == (
        "employee_csv_export=preview employees=1\ncsv_changes=none\n"
    )


def test_employee_csv_export_apply_replaces_csv_atomically(tmp_path: Path, capsys):
    from division_overtime.cli import _export_employees
    from division_overtime.employees import load_employees

    db = Database(tmp_path / "test.sqlite3")
    _seed_employee(db)
    csv_path = tmp_path / "employeeKey.csv"
    csv_path.write_text("existing", encoding="utf-8")

    result = _export_employees(db, csv_path, apply=True)

    assert result == 0
    employees = load_employees(csv_path)
    assert len(employees) == 1
    assert employees[0].code == "00001"
    assert capsys.readouterr().out == "employee_csv_export=applied employees=1\n"
    assert list(tmp_path.glob(".employeeKey.csv.*.tmp")) == []


def test_employee_csv_export_rejects_zero_enabled_employees(tmp_path: Path):
    from division_overtime.cli import _export_employees

    db = Database(tmp_path / "test.sqlite3")
    _seed_employee(db, enabled=False)
    csv_path = tmp_path / "employeeKey.csv"
    csv_path.write_text("existing", encoding="utf-8")

    with pytest.raises(Exception, match="No enabled employees"):
        _export_employees(db, csv_path, apply=True)

    assert csv_path.read_text(encoding="utf-8") == "existing"


def test_employee_data_consistency_returns_zero_when_data_matches(
    tmp_path: Path, employee_csv: Path, capsys
):
    from division_overtime.cli import _check_employee_consistency

    db = Database(tmp_path / "test.sqlite3")
    _seed_employee(db)

    result = _check_employee_consistency(db, employee_csv)

    assert result == 0
    assert capsys.readouterr().out == (
        "employee_data_consistency=ok database_employees=1 csv_employees=1\n"
    )


def test_employee_data_consistency_reports_missing_and_changed_records(tmp_path: Path, capsys):
    from division_overtime.cli import _check_employee_consistency

    db = Database(tmp_path / "test.sqlite3")
    _seed_employee(db)
    with db.transaction() as conn:
        conn.execute(
            """
            INSERT INTO employees(
                code, kot_key, last_name, first_name, division_code,
                division_name, email, personal_target_minutes,
                is_enabled, created_at, updated_at
            )
            VALUES('00002', 'secret-db-only', '鈴木', '花子', '300',
                   '営業部', 's@example.com', NULL, 1, 'now', 'now')
            """
        )

    csv_path = tmp_path / "employeeKey.csv"
    csv_path.write_text(
        "社員番号,キー,氏,名,メールアドレス,部署コード,部署名,個人別残業上限分\n"
        "00001,secret-csv,田中,太郎,changed@example.com,300,営業部,1200\n"
        "00003,secret-csv-only,佐藤,次郎,sato@example.com,300,営業部,\n",
        encoding="utf-8",
    )

    result = _check_employee_consistency(db, csv_path)

    assert result == 1
    output = capsys.readouterr().out
    assert output == (
        "employee_data_consistency=mismatch database_employees=2 csv_employees=2\n"
        "database_only employee_code=00002\n"
        "csv_only employee_code=00003\n"
        "field_mismatch employee_code=00001 fields=kot_key,email\n"
    )
    assert "secret-db-only" not in output
    assert "secret-csv" not in output
    assert "secret-csv-only" not in output


def test_employee_data_consistency_is_read_only(tmp_path: Path, employee_csv: Path):
    from division_overtime.cli import _check_employee_consistency

    db = Database(tmp_path / "test.sqlite3")
    _seed_employee(db)
    before_csv = employee_csv.read_bytes()
    with db.connect() as conn:
        before_row = dict(conn.execute("SELECT * FROM employees WHERE code='00001'").fetchone())

    result = _check_employee_consistency(db, employee_csv)

    assert result == 0
    assert employee_csv.read_bytes() == before_csv
    with db.connect() as conn:
        after_row = dict(conn.execute("SELECT * FROM employees WHERE code='00001'").fetchone())
    assert after_row == before_row


def test_employee_data_consistency_json_returns_machine_readable_result(tmp_path: Path, capsys):
    import json

    from division_overtime.cli import _check_employee_consistency

    db = Database(tmp_path / "test.sqlite3")
    _seed_employee(db)
    with db.transaction() as conn:
        conn.execute(
            """
            INSERT INTO employees(
                code, kot_key, last_name, first_name, division_code,
                division_name, email, personal_target_minutes,
                is_enabled, created_at, updated_at
            )
            VALUES('00002', 'secret-db-only', '鈴木', '花子', '300',
                   '営業部', 's@example.com', NULL, 1, 'now', 'now')
            """
        )

    csv_path = tmp_path / "employeeKey.csv"
    csv_path.write_text(
        "社員番号,キー,氏,名,メールアドレス,部署コード,部署名,個人別残業上限分\n"
        "00001,secret-csv,田中,太郎,changed@example.com,300,営業部,1200\n"
        "00003,secret-csv-only,佐藤,次郎,sato@example.com,300,営業部,\n",
        encoding="utf-8",
    )

    result = _check_employee_consistency(db, csv_path, json_output=True)

    assert result == 1
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload == {
        "status": "mismatch",
        "databaseEmployees": 2,
        "csvEmployees": 2,
        "databaseOnlyEmployeeCodes": ["00002"],
        "csvOnlyEmployeeCodes": ["00003"],
        "mismatchedEmployees": [{"employeeCode": "00001", "fields": ["kot_key", "email"]}],
    }
    assert "secret-db-only" not in output
    assert "secret-csv" not in output
    assert "secret-csv-only" not in output
    assert "changed@example.com" not in output


def test_employee_data_consistency_json_reports_error(tmp_path: Path, capsys):
    import json

    from division_overtime.cli import _check_employee_consistency

    db = Database(tmp_path / "test.sqlite3")
    csv_path = tmp_path / "employeeKey.csv"

    result = _check_employee_consistency(db, csv_path, json_output=True)

    assert result == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    assert payload["databaseEmployees"] is None
    assert payload["csvEmployees"] is None
    assert payload["databaseOnlyEmployeeCodes"] == []
    assert payload["csvOnlyEmployeeCodes"] == []
    assert payload["mismatchedEmployees"] == []
    assert "Database is not initialized" in payload["error"]
