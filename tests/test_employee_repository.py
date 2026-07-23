from datetime import datetime
from zoneinfo import ZoneInfo

from division_overtime.database import Database
from division_overtime.employee_repository import EmployeeRepository
from division_overtime.models import Employee


def test_employee_repository_upserts_csv_fields_and_preserves_management_fields(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.initialize()
    repository = EmployeeRepository(db)
    now = datetime(2026, 7, 23, 9, 30, tzinfo=ZoneInfo("Asia/Tokyo"))

    repository.upsert_many(
        [
            Employee(
                code="00001",
                employee_key="key-1",
                last_name="田中",
                first_name="太郎",
                email="t@example.com",
                division_code="300",
                division_name="営業部",
                personal_target_minutes=1200,
            )
        ],
        now,
    )

    with db.transaction() as conn:
        conn.execute(
            """
            UPDATE employees
            SET is_enabled=0, disabled_reason='休職中', note='管理画面入力'
            WHERE code='00001'
            """
        )

    later = datetime(2026, 7, 23, 10, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    repository.upsert_many(
        [
            Employee(
                code="00001",
                employee_key="key-2",
                last_name="田中",
                first_name="太郎",
                email="new@example.com",
                division_code="300",
                division_name="営業本部",
                personal_target_minutes=1500,
            )
        ],
        later,
    )

    with db.connect() as conn:
        row = conn.execute("SELECT * FROM employees WHERE code='00001'").fetchone()

    assert row["kot_key"] == "key-2"
    assert row["email"] == "new@example.com"
    assert row["division_name"] == "営業本部"
    assert row["personal_target_minutes"] == 1500
    assert row["is_enabled"] == 0
    assert row["disabled_reason"] == "休職中"
    assert row["note"] == "管理画面入力"
    assert row["created_at"] == now.isoformat()
    assert row["updated_at"] == later.isoformat()


def test_employee_repository_imports_csv(tmp_path):
    csv_path = tmp_path / "employeeKey.csv"
    csv_path.write_text(
        "社員番号,キー,氏,名,メールアドレス,部署コード,部署名,個人別残業上限分\n"
        "00001,key,田中,太郎,t@example.com,300,営業部,1200\n",
        encoding="utf-8",
    )
    db = Database(tmp_path / "test.sqlite3")
    db.initialize()
    repository = EmployeeRepository(db)
    now = datetime(2026, 7, 23, 9, 30, tzinfo=ZoneInfo("Asia/Tokyo"))

    imported = repository.import_csv(csv_path, now)

    assert imported == 1
    assert repository.count() == 1
