import os
import sqlite3
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
    output = capsys.readouterr().out
    assert "employee_csv_export=applied status=success" in output
    assert "employees=1" in output
    assert f"output_path={csv_path}" in output
    assert f"backup_path={tmp_path / 'backups' / 'employee-csv'}" in output
    assert "generated_at=" in output
    assert "removed_backups=0" in output
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
        "employee_count.database_enabled=1\n"
        "employee_count.csv_records=1\n"
        "employee_consistency=ok mismatches=0\n"
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
        "employee_count.database_enabled=2\n"
        "employee_count.csv_records=2\n"
        "employee_consistency=mismatch mismatches=3\n"
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


def test_record_employee_consistency_appends_jsonl(tmp_path: Path, employee_csv: Path, capsys):
    import json

    from division_overtime.cli import _record_employee_consistency

    db = Database(tmp_path / "test.sqlite3")
    _seed_employee(db)
    history_path = tmp_path / "history" / "employee-consistency-history.jsonl"

    first = _record_employee_consistency(db, employee_csv, history_path)
    second = _record_employee_consistency(db, employee_csv, history_path)

    assert first == 0
    assert second == 0
    records = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 2
    assert records[0]["status"] == "ok"
    assert records[0]["databaseEmployees"] == 1
    assert records[0]["csvEmployees"] == 1
    assert records[0]["recordedAt"]
    assert records[1]["recordedAt"]
    assert capsys.readouterr().out == (
        f"employee_data_consistency_recorded status=ok path={history_path}\n"
        f"employee_data_consistency_recorded status=ok path={history_path}\n"
    )


def test_record_employee_consistency_records_mismatch_without_secrets(tmp_path: Path, capsys):
    import json

    from division_overtime.cli import _record_employee_consistency

    db = Database(tmp_path / "test.sqlite3")
    _seed_employee(db)
    csv_path = tmp_path / "employeeKey.csv"
    csv_path.write_text(
        "社員番号,キー,氏,名,メールアドレス,部署コード,部署名,個人別残業上限分\n"
        "00001,secret-csv,田中,太郎,changed@example.com,300,営業部,1200\n",
        encoding="utf-8",
    )
    history_path = tmp_path / "employee-consistency-history.jsonl"

    result = _record_employee_consistency(db, csv_path, history_path)

    assert result == 1
    content = history_path.read_text(encoding="utf-8")
    payload = json.loads(content)
    assert payload["status"] == "mismatch"
    assert payload["mismatchedEmployees"] == [
        {"employeeCode": "00001", "fields": ["kot_key", "email"]}
    ]
    assert "secret-csv" not in content
    assert "changed@example.com" not in content


def test_record_employee_consistency_records_error(tmp_path: Path):
    import json

    from division_overtime.cli import _record_employee_consistency

    db = Database(tmp_path / "test.sqlite3")
    csv_path = tmp_path / "employeeKey.csv"
    history_path = tmp_path / "nested" / "employee-consistency-history.jsonl"

    result = _record_employee_consistency(db, csv_path, history_path)

    assert result == 1
    payload = json.loads(history_path.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert "Database is not initialized" in payload["error"]


def test_run_parser_defaults_source_to_manual():
    from division_overtime.cli import _parser

    args = _parser().parse_args(["run", "weekly"])

    assert args.source == "manual"


def test_run_parser_accepts_explicit_test_source():
    from division_overtime.cli import _parser

    args = _parser().parse_args(["run", "threshold", "--dry-run", "--source", "test"])

    assert args.dry_run is True
    assert args.source == "test"


def test_database_parser_accepts_backup_paths():
    from division_overtime.cli import _parser

    args = _parser().parse_args(
        ["database", "backup", "--path", "var/custom.sqlite3", "--output", "backup.sqlite3"]
    )

    assert args.path == Path("var/custom.sqlite3")
    assert args.output == Path("backup.sqlite3")


def test_database_status_prints_observability(tmp_path: Path, capsys):
    from argparse import Namespace

    from division_overtime.cli import _run_database_command

    db_path = tmp_path / "custom.sqlite3"
    Database(db_path).initialize()
    args = Namespace(
        root=tmp_path,
        action="status",
        path=Path("custom.sqlite3"),
        output=None,
    )

    result = _run_database_command(args)

    assert result == 0
    output = capsys.readouterr().out
    assert f"database={db_path}" in output
    assert "database_bytes=" in output
    assert "wal_bytes=" in output
    assert "shm_bytes=" in output
    assert "total_bytes=" in output
    assert "table_count.execution_runs=0" in output
    assert "table_count.notification_attempts=0" in output
    assert "integrity_check=ok" in output


def test_database_backup_uses_explicit_output(tmp_path: Path, capsys):
    from argparse import Namespace

    from division_overtime.cli import _run_database_command

    db_path = tmp_path / "custom.sqlite3"
    Database(db_path).initialize()
    args = Namespace(
        root=tmp_path,
        action="backup",
        path=Path("custom.sqlite3"),
        output=Path("backups/manual.sqlite3"),
    )

    result = _run_database_command(args)

    destination = tmp_path / "backups" / "manual.sqlite3"
    assert result == 0
    assert destination.exists()
    if os.name != "nt":
        assert destination.stat().st_mode & 0o777 == 0o600
    assert "database_backup=ok" in capsys.readouterr().out


def test_database_migrate_backs_up_old_schema_and_preserves_data(tmp_path: Path, capsys):
    from argparse import Namespace

    from division_overtime.cli import _run_database_command

    db_path = tmp_path / "custom.sqlite3"
    database = Database(db_path)
    database.initialize()
    with database.transaction() as conn:
        conn.execute("UPDATE schema_meta SET value='7' WHERE key='schema_version'")
        conn.execute("DROP TABLE kot_sync_divisions")
        conn.execute(
            "INSERT INTO employees("
            "code, kot_key, last_name, first_name, division_code, division_name, "
            "is_enabled, kot_exists, created_at, updated_at"
            ") VALUES(?, ?, ?, ?, ?, ?, 1, 1, ?, ?)",
            ("00001", "key-1", "Test", "User", "100", "Division", "now", "now"),
        )
    args = Namespace(
        root=tmp_path,
        action="migrate",
        path=Path("custom.sqlite3"),
        output=Path("backups/before.sqlite3"),
    )

    result = _run_database_command(args)

    backup = tmp_path / "backups" / "before.sqlite3"
    assert result == 0
    assert backup.exists()
    with sqlite3.connect(backup) as conn:
        assert (
            conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0]
            == "7"
        )
        assert conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 1
    with database.connect_readonly() as conn:
        assert (
            conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0]
            == "8"
        )
        assert conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 1
        assert (
            conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='kot_sync_divisions'"
            ).fetchone()[0]
            == "kot_sync_divisions"
        )
    output = capsys.readouterr().out
    assert "database_migration_backup=ok" in output
    assert "schema_version_before=7" in output
    assert "schema_version_after=8" in output
    assert "database_migration=ok" in output
    assert "integrity_check=ok" in output


def test_database_migrate_is_idempotent(tmp_path: Path):
    from argparse import Namespace

    from division_overtime.cli import _run_database_command

    db_path = tmp_path / "custom.sqlite3"
    Database(db_path).initialize()
    args = Namespace(
        root=tmp_path,
        action="migrate",
        path=Path("custom.sqlite3"),
        output=Path("backups/before.sqlite3"),
    )

    assert _run_database_command(args) == 0
    args.output = Path("backups/before-second.sqlite3")
    assert _run_database_command(args) == 0
    assert Database(db_path).is_initialized_readonly() is True


def test_database_migrate_refuses_missing_database_without_creating_file(tmp_path: Path):
    from argparse import Namespace

    from division_overtime.cli import _run_database_command

    db_path = tmp_path / "missing.sqlite3"
    args = Namespace(
        root=tmp_path,
        action="migrate",
        path=Path("missing.sqlite3"),
        output=None,
    )

    with pytest.raises(RuntimeError, match="Database file does not exist"):
        _run_database_command(args)

    assert db_path.exists() is False
    assert list((tmp_path / "var" / "backups").glob("**/*")) == []


def test_database_migrate_stops_before_schema_change_when_backup_fails(tmp_path: Path, monkeypatch):
    from argparse import Namespace

    from division_overtime.cli import _run_database_command

    db_path = tmp_path / "custom.sqlite3"
    database = Database(db_path)
    database.initialize()
    with database.transaction() as conn:
        conn.execute("UPDATE schema_meta SET value='7' WHERE key='schema_version'")
        conn.execute("DROP TABLE kot_sync_divisions")

    def fail_backup(_destination: Path) -> None:
        raise RuntimeError("forced backup failure")

    monkeypatch.setattr(database, "backup_to", fail_backup)
    monkeypatch.setattr("division_overtime.cli._database_for_args", lambda _root, _path: database)
    args = Namespace(
        root=tmp_path,
        action="migrate",
        path=Path("custom.sqlite3"),
        output=Path("backups/before.sqlite3"),
    )

    with pytest.raises(RuntimeError, match="forced backup failure"):
        _run_database_command(args)

    with database.connect_readonly() as conn:
        assert (
            conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0]
            == "7"
        )
        assert (
            conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='kot_sync_divisions'"
            ).fetchone()
            is None
        )


def test_database_migrate_prunes_oldest_default_deploy_backup(tmp_path: Path, capsys):
    from argparse import Namespace
    from datetime import datetime, timedelta

    from division_overtime.cli import _run_database_command

    db_path = tmp_path / "custom.sqlite3"
    Database(db_path).initialize()
    backup_root = tmp_path / "var" / "backups" / "deploy-database"
    start = datetime(2026, 7, 1, 0, 0)
    oldest = None
    for index in range(30):
        generation = backup_root / (start + timedelta(hours=index)).strftime("%Y%m%d_%H%M%S_%f")
        generation.mkdir(parents=True)
        (generation / "division_overtime.sqlite3").write_text("backup", encoding="utf-8")
        oldest = generation if oldest is None else oldest
    args = Namespace(
        root=tmp_path,
        action="migrate",
        path=Path("custom.sqlite3"),
        output=None,
    )

    assert _run_database_command(args) == 0

    assert oldest is not None
    assert oldest.exists() is False
    assert len([path for path in backup_root.iterdir() if path.is_dir()]) == 30
    output = capsys.readouterr().out
    assert "database_migration_backup_prune=ok" in output
    assert "removed=1" in output
    assert "retained=30" in output


def test_database_migrate_prune_failure_does_not_fail_migration(
    tmp_path: Path, monkeypatch, caplog
):
    from argparse import Namespace

    from division_overtime.cli import _run_database_command

    db_path = tmp_path / "custom.sqlite3"
    Database(db_path).initialize()

    def fail_prune(*_args, **_kwargs):
        raise OSError("simulated prune failure")

    monkeypatch.setattr("division_overtime.cli.prune_backup_directories", fail_prune)
    args = Namespace(
        root=tmp_path,
        action="migrate",
        path=Path("custom.sqlite3"),
        output=None,
    )

    assert _run_database_command(args) == 0
    assert Database(db_path).is_initialized_readonly() is True
    assert "database_migration_backup_prune=failed" in caplog.text


def test_backups_status_prints_read_only_summary(tmp_path: Path, capsys) -> None:
    from argparse import Namespace
    from datetime import datetime

    from division_overtime.cli import _run_backups_command

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.toml").write_text(
        '[app]\ndatabase_path = "var/division_overtime.sqlite3"\n'
        'employee_csv = "data/employeeKey.csv"\n',
        encoding="utf-8",
    )
    backup_root = tmp_path / "var" / "backups" / "deploy-database"
    generation = backup_root / datetime(2026, 8, 3, 17, 15, 55, 367173).strftime("%Y%m%d_%H%M%S_%f")
    generation.mkdir(parents=True)
    (generation / "division_overtime.sqlite3").write_text("backup", encoding="utf-8")
    before = (generation / "division_overtime.sqlite3").read_bytes()

    assert _run_backups_command(Namespace(root=tmp_path, action="status")) == 0

    output = capsys.readouterr().out
    assert "backup.deploy_database.count=1" in output
    assert "backup.deploy_database.retention=30" in output
    assert "backup.deploy_database.latest=20260803_171555_367173" in output
    assert "backup.deploy_database.ignored=0" in output
    assert "backup.deploy_database.status=ok" in output
    assert "backup.employee_delete.count=0" in output
    assert "backup.employee_csv.count=0" in output
    assert "backup.kot_sync.count=0" in output
    assert (generation / "division_overtime.sqlite3").read_bytes() == before
