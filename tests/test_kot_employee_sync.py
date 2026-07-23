from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from division_overtime.database import Database
from division_overtime.employee_repository import EmployeeRepository
from division_overtime.kot_employee_sync import KotEmployeeSyncService, parse_kot_employees
from division_overtime.models import Employee


class FakeClient:
    def fetch(self):
        return parse_kot_employees(
            [
                {
                    "code": "00001",
                    "key": "new-key",
                    "lastName": "田中",
                    "firstName": "太郎",
                    "divisionCode": "301",
                    "divisionName": "開発部",
                    "employeeGroups": [],
                },
                {
                    "code": "00002",
                    "key": "key-2",
                    "lastName": "佐藤",
                    "firstName": "花子",
                    "divisionCode": "301",
                    "divisionName": "開発部",
                    "employeeGroups": [],
                },
            ]
        )


def test_preview_does_not_modify_database_or_csv(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    EmployeeRepository(db).upsert_many(
        [Employee("00001", "old-key", "田中", "太郎", "", "300", "営業部")],
        datetime.now(ZoneInfo("Asia/Tokyo")),
    )
    csv = tmp_path / "employeeKey.csv"
    csv.write_text("original", encoding="utf-8")
    service = KotEmployeeSyncService(db, csv, FakeClient(), ("300", "301"))

    preview_id, differences = service.preview()

    assert preview_id
    assert {d.code: d.action for d in differences} == {"00001": "update", "00002": "create"}
    assert csv.read_text(encoding="utf-8") == "original"
    with db.connect() as conn:
        assert (
            conn.execute("SELECT division_code FROM employees WHERE code='00001'").fetchone()[0]
            == "300"
        )


def test_apply_updates_database_and_csv_without_returning_key(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    EmployeeRepository(db).upsert_many(
        [Employee("00001", "old-key", "田中", "太郎", "", "300", "営業部")],
        datetime.now(ZoneInfo("Asia/Tokyo")),
    )
    csv = tmp_path / "employeeKey.csv"
    service = KotEmployeeSyncService(db, csv, FakeClient(), ("300", "301"))
    preview_id, _ = service.preview()

    counts = service.apply(
        preview_id, ["00001", "00002"], "hiro", datetime.now(ZoneInfo("Asia/Tokyo"))
    )

    assert counts == {"created": 1, "updated": 1, "disabled": 0}
    assert "new-key" in csv.read_text(encoding="utf-8-sig")
    with db.connect() as conn:
        assert (
            conn.execute("SELECT kot_key FROM employees WHERE code='00001'").fetchone()[0]
            == "new-key"
        )
        assert conn.execute("SELECT COUNT(*) FROM kot_sync_runs").fetchone()[0] == 1


def test_preview_filters_to_configured_divisions_and_reports_counts(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    EmployeeRepository(db).upsert_many(
        [
            Employee("00001", "old-key", "田中", "太郎", "", "300", "本部"),
            Employee("00003", "key-3", "鈴木", "次郎", "", "999", "対象外"),
        ],
        datetime.now(ZoneInfo("Asia/Tokyo")),
    )
    csv = tmp_path / "employeeKey.csv"
    service = KotEmployeeSyncService(db, csv, FakeClient(), ("301",))

    preview_id, differences = service.preview()

    assert {item.code for item in differences} == {"00001", "00002"}
    assert service.preview_metadata(preview_id) == {
        "fetchedCount": 2,
        "targetCount": 2,
        "targetDivisionCodes": ["301"],
    }


def test_empty_target_divisions_are_rejected(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()

    try:
        KotEmployeeSyncService(db, tmp_path / "employeeKey.csv", FakeClient(), ())
    except Exception as exc:
        assert "division code" in str(exc)
    else:
        raise AssertionError("empty target divisions must be rejected")
