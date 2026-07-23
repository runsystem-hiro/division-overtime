from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from division_overtime.database import Database
from division_overtime.employee_repository import EmployeeRepository
from division_overtime.employee_source import CsvEmployeeSource, SqliteEmployeeSource
from division_overtime.models import Employee


def test_sqlite_employee_source_matches_csv_source(tmp_path: Path):
    csv_path = tmp_path / "employeeKey.csv"
    csv_path.write_text(
        "社員番号,キー,氏,名,メールアドレス,部署コード,部署名,個人別残業上限分\n"
        "00001,key-1,田中,太郎,t@example.com,300,営業部,1200\n"
        "00002,key-2,佐藤,次郎,,400,開発部,\n",
        encoding="utf-8",
    )
    csv_employees = CsvEmployeeSource(csv_path).list_employees()

    database = Database(tmp_path / "test.sqlite3")
    database.initialize()
    repository = EmployeeRepository(database)
    repository.upsert_many(
        csv_employees,
        datetime(2026, 7, 23, 15, 45, tzinfo=ZoneInfo("Asia/Tokyo")),
    )

    assert SqliteEmployeeSource(repository).list_employees() == csv_employees


def test_sqlite_employee_source_excludes_disabled_employees(tmp_path: Path):
    database = Database(tmp_path / "test.sqlite3")
    database.initialize()
    repository = EmployeeRepository(database)
    repository.upsert_many(
        [
            Employee("00002", "key-2", "佐藤", "次郎", "", "400", "開発部"),
            Employee("00001", "key-1", "田中", "太郎", "t@example.com", "300", "営業部", 1200),
        ],
        datetime(2026, 7, 23, 15, 45, tzinfo=ZoneInfo("Asia/Tokyo")),
    )
    with database.transaction() as conn:
        conn.execute("UPDATE employees SET is_enabled=0 WHERE code='00002'")

    employees = SqliteEmployeeSource(repository).list_employees()

    assert employees == [
        Employee("00001", "key-1", "田中", "太郎", "t@example.com", "300", "営業部", 1200)
    ]
