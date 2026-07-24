import os
import stat
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

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

    assert counts["created"] == 1
    assert counts["updated"] == 1
    assert counts["disabled"] == 0
    assert Path(str(counts["backupPath"])).exists()
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


def test_preview_reports_changed_fields_without_exposing_key(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    EmployeeRepository(db).upsert_many(
        [Employee("00001", "old-key", "田中", "太郎", "", "301", "開発部")],
        datetime.now(ZoneInfo("Asia/Tokyo")),
    )
    service = KotEmployeeSyncService(
        db,
        tmp_path / "employeeKey.csv",
        FakeClient(),
        ("301",),
    )

    _, differences = service.preview()

    difference = next(item for item in differences if item.code == "00001")
    assert difference.action == "update"
    assert "kotKey" in difference.changed_fields
    assert "new-key" not in repr(difference.current)
    assert "new-key" not in repr(difference.proposed)


def test_apply_creates_database_and_csv_backup(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    EmployeeRepository(db).upsert_many(
        [Employee("00001", "old-key", "田中", "太郎", "", "300", "営業部")],
        datetime.now(ZoneInfo("Asia/Tokyo")),
    )
    csv = tmp_path / "employeeKey.csv"
    csv.write_text("original-csv", encoding="utf-8")
    backup_root = tmp_path / "backups"
    service = KotEmployeeSyncService(
        db,
        csv,
        FakeClient(),
        ("300", "301"),
        backup_root=backup_root,
    )
    preview_id, _ = service.preview()
    now = datetime(2026, 7, 23, 13, 30, 0, tzinfo=ZoneInfo("Asia/Tokyo"))

    result = service.apply(preview_id, ["00001"], "hiro", now)

    backup_dirs = list(backup_root.iterdir())
    assert len(backup_dirs) == 1
    backup_dir = backup_dirs[0]
    assert result["backupPath"] == str(backup_dir)
    database_backup = backup_dir / "db.sqlite3"
    csv_backup = backup_dir / "employeeKey.csv"

    assert database_backup.exists()
    assert csv_backup.read_text(encoding="utf-8") == "original-csv"
    with Database(database_backup).connect() as conn:
        assert (
            conn.execute("SELECT kot_key FROM employees WHERE code='00001'").fetchone()[0]
            == "old-key"
        )


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions are not available")
def test_apply_backup_uses_owner_only_permissions(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    EmployeeRepository(db).upsert_many(
        [Employee("00001", "old-key", "田中", "太郎", "", "300", "営業部")],
        datetime.now(ZoneInfo("Asia/Tokyo")),
    )
    csv = tmp_path / "employeeKey.csv"
    csv.write_text("original-csv", encoding="utf-8")
    backup_root = tmp_path / "backups"
    service = KotEmployeeSyncService(
        db,
        csv,
        FakeClient(),
        ("300", "301"),
        backup_root=backup_root,
    )
    preview_id, _ = service.preview()

    service.apply(
        preview_id,
        ["00001"],
        "hiro",
        datetime(2026, 7, 23, 13, 30, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
    )

    backup_dir = next(backup_root.iterdir())
    database_backup = backup_dir / "db.sqlite3"
    csv_backup = backup_dir / "employeeKey.csv"

    assert stat.S_IMODE(backup_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(database_backup.stat().st_mode) == 0o600
    assert stat.S_IMODE(csv_backup.stat().st_mode) == 0o600


def test_apply_backup_allows_missing_csv(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    EmployeeRepository(db).upsert_many(
        [Employee("00001", "old-key", "田中", "太郎", "", "300", "営業部")],
        datetime.now(ZoneInfo("Asia/Tokyo")),
    )
    csv = tmp_path / "employeeKey.csv"
    backup_root = tmp_path / "backups"
    service = KotEmployeeSyncService(
        db,
        csv,
        FakeClient(),
        ("300", "301"),
        backup_root=backup_root,
    )
    preview_id, _ = service.preview()

    service.apply(
        preview_id,
        ["00001"],
        "hiro",
        datetime(2026, 7, 23, 13, 30, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
    )

    backup_dir = next(backup_root.iterdir())
    assert (backup_dir / "db.sqlite3").exists()
    assert not (backup_dir / "employeeKey.csv").exists()


def test_apply_stops_before_update_when_backup_fails(tmp_path: Path, monkeypatch):
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    EmployeeRepository(db).upsert_many(
        [Employee("00001", "old-key", "田中", "太郎", "", "300", "営業部")],
        datetime.now(ZoneInfo("Asia/Tokyo")),
    )
    csv = tmp_path / "employeeKey.csv"
    csv.write_text("original", encoding="utf-8")
    service = KotEmployeeSyncService(
        db,
        csv,
        FakeClient(),
        ("300", "301"),
        backup_root=tmp_path / "backups",
    )
    preview_id, _ = service.preview()

    def fail_backup(destination: Path) -> None:
        raise OSError("backup storage unavailable")

    monkeypatch.setattr(db, "backup_to", fail_backup)

    try:
        service.apply(
            preview_id,
            ["00001"],
            "hiro",
            datetime.now(ZoneInfo("Asia/Tokyo")),
        )
    except Exception as exc:
        assert "backup failed" in str(exc).lower()
    else:
        raise AssertionError("apply must fail when backup creation fails")

    assert csv.read_text(encoding="utf-8") == "original"
    with db.connect() as conn:
        assert (
            conn.execute("SELECT kot_key FROM employees WHERE code='00001'").fetchone()[0]
            == "old-key"
        )
        assert conn.execute("SELECT COUNT(*) FROM kot_sync_runs").fetchone()[0] == 0
