import os
import shutil
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
        run = conn.execute(
            "SELECT backup_path FROM kot_sync_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert run["backup_path"] == str(counts["backupPath"])


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


def test_preview_omits_already_disabled_employee_missing_from_kot(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    repository = EmployeeRepository(db)
    repository.upsert_many(
        [Employee("00003", "key-3", "鈴木", "次郎", "", "301", "開発部")],
        datetime.now(ZoneInfo("Asia/Tokyo")),
    )
    with db.transaction() as conn:
        conn.execute(
            "UPDATE employees SET is_enabled=0, disabled_reason='手動無効化' WHERE code='00003'"
        )
    service = KotEmployeeSyncService(
        db,
        tmp_path / "employeeKey.csv",
        FakeClient(),
        ("301",),
    )

    _, differences = service.preview()

    assert "00003" not in {item.code for item in differences}


def test_preview_omits_already_disabled_resigned_employee(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    repository = EmployeeRepository(db)
    repository.upsert_many(
        [Employee("00001", "old-key", "田中", "太郎", "", "301", "開発部")],
        datetime.now(ZoneInfo("Asia/Tokyo")),
    )
    with db.transaction() as conn:
        conn.execute(
            "UPDATE employees SET is_enabled=0, disabled_reason='KOT退職済み' WHERE code='00001'"
        )

    class ResignedClient:
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
                        "resignationDate": "2026-07-23",
                    }
                ]
            )

    service = KotEmployeeSyncService(
        db,
        tmp_path / "employeeKey.csv",
        ResignedClient(),
        ("301",),
    )

    _, differences = service.preview()

    assert differences == []


def test_preview_keeps_enabled_resigned_employee_as_disable(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    EmployeeRepository(db).upsert_many(
        [Employee("00001", "old-key", "田中", "太郎", "", "301", "開発部")],
        datetime.now(ZoneInfo("Asia/Tokyo")),
    )

    class ResignedClient:
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
                        "resignationDate": "2026-07-23",
                    }
                ]
            )

    service = KotEmployeeSyncService(
        db,
        tmp_path / "employeeKey.csv",
        ResignedClient(),
        ("301",),
    )

    _, differences = service.preview()

    assert [(item.code, item.action) for item in differences] == [("00001", "disable")]


def test_preview_keeps_enabled_employee_missing_from_kot_as_disable(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    EmployeeRepository(db).upsert_many(
        [Employee("00003", "key-3", "鈴木", "次郎", "", "301", "開発部")],
        datetime.now(ZoneInfo("Asia/Tokyo")),
    )
    service = KotEmployeeSyncService(
        db,
        tmp_path / "employeeKey.csv",
        FakeClient(),
        ("301",),
    )

    _, differences = service.preview()

    difference = next(item for item in differences if item.code == "00003")
    assert difference.action == "disable"


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


def test_preview_and_apply_reactivate_preserves_local_settings(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    EmployeeRepository(db).upsert_many(
        [
            Employee(
                "00001",
                "old-key",
                "旧姓",
                "太郎",
                "local@example.com",
                "301",
                "旧部署",
                1500,
            )
        ],
        datetime.now(ZoneInfo("Asia/Tokyo")),
    )
    with db.transaction() as conn:
        conn.execute(
            "UPDATE employees SET is_enabled=0, disabled_reason='手動無効化', note='保持メモ' "
            "WHERE code='00001'"
        )

    class ReactivationClient:
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
                        "employeeGroups": [{"code": "g1", "name": "開発"}],
                    }
                ]
            )

    csv = tmp_path / "employeeKey.csv"
    service = KotEmployeeSyncService(db, csv, ReactivationClient(), ("301",))

    preview_id, differences = service.preview()

    assert [(item.code, item.action) for item in differences] == [("00001", "reactivate")]
    assert "通知対象へ再有効化" in differences[0].warnings

    result = service.apply(
        preview_id,
        ["00001"],
        "hiro",
        datetime(2026, 7, 24, 13, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
    )

    assert result["reactivated"] == 1
    with db.connect() as conn:
        employee = conn.execute("SELECT * FROM employees WHERE code='00001'").fetchone()
        run = conn.execute("SELECT * FROM kot_sync_runs ORDER BY id DESC LIMIT 1").fetchone()
    assert employee["is_enabled"] == 1
    assert employee["disabled_reason"] is None
    assert employee["email"] == "local@example.com"
    assert employee["personal_target_minutes"] == 1500
    assert employee["note"] == "保持メモ"
    assert employee["kot_key"] == "new-key"
    assert employee["last_name"] == "田中"
    assert employee["division_name"] == "開発部"
    assert employee["kot_group_codes"] == "g1"
    assert run["reactivated_count"] == 1
    assert "local@example.com" in csv.read_text(encoding="utf-8-sig")


def test_reactivation_warns_when_notification_settings_are_missing(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    EmployeeRepository(db).upsert_many(
        [Employee("00001", "old-key", "田中", "太郎", "", "301", "開発部")],
        datetime.now(ZoneInfo("Asia/Tokyo")),
    )
    with db.transaction() as conn:
        conn.execute("UPDATE employees SET is_enabled=0 WHERE code='00001'")
    service = KotEmployeeSyncService(db, tmp_path / "employeeKey.csv", FakeClient(), ("301",))

    _, differences = service.preview()

    target = next(item for item in differences if item.code == "00001")
    assert target.action == "reactivate"
    assert "メールアドレス未設定" in target.warnings
    assert "個人上限分未設定" in target.warnings


def test_successful_apply_prunes_only_managed_backups_to_latest_30(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    EmployeeRepository(db).upsert_many(
        [Employee("00001", "old-key", "田中", "太郎", "", "300", "営業部")],
        datetime.now(ZoneInfo("Asia/Tokyo")),
    )
    backup_root = tmp_path / "backups"
    backup_root.mkdir()
    for index in range(31):
        (backup_root / f"20260701_0000{index:02d}_000000").mkdir()
    unmanaged = backup_root / "manual-keep"
    unmanaged.mkdir()
    service = KotEmployeeSyncService(
        db,
        tmp_path / "employeeKey.csv",
        FakeClient(),
        ("300", "301"),
        backup_root=backup_root,
    )
    preview_id, _ = service.preview()

    service.apply(
        preview_id,
        ["00001"],
        "hiro",
        datetime(2026, 7, 24, 13, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
    )

    managed = [path for path in backup_root.iterdir() if service._is_managed_backup_dir(path.name)]
    assert len(managed) == 30
    assert unmanaged.exists()


def test_backup_prune_failure_does_not_fail_successful_apply(tmp_path: Path, monkeypatch):
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    EmployeeRepository(db).upsert_many(
        [Employee("00001", "old-key", "田中", "太郎", "", "300", "営業部")],
        datetime.now(ZoneInfo("Asia/Tokyo")),
    )
    backup_root = tmp_path / "backups"
    backup_root.mkdir()
    for index in range(30):
        (backup_root / f"20260701_0000{index:02d}_000000").mkdir()
    service = KotEmployeeSyncService(
        db,
        tmp_path / "employeeKey.csv",
        FakeClient(),
        ("300", "301"),
        backup_root=backup_root,
    )
    preview_id, _ = service.preview()
    original_rmtree = shutil.rmtree

    def fail_for_oldest(path: Path, *args, **kwargs):
        if Path(path).name == "20260701_000000_000000":
            raise OSError("cannot remove")
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", fail_for_oldest)
    result = service.apply(
        preview_id,
        ["00001"],
        "hiro",
        datetime(2026, 7, 24, 13, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
    )

    assert result["updated"] == 1
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM kot_sync_runs").fetchone()[0] == 1
