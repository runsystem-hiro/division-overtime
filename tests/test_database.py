import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from division_overtime.database import Database


def test_database_initialization_creates_employee_schema_version_8(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.initialize()
    assert db.integrity_check() == "ok"


def test_notification_unique_constraint_prevents_duplicate(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.initialize()
    now = datetime(2026, 7, 22, 10, 30, tzinfo=ZoneInfo("Asia/Tokyo"))
    db.start_run("run-1", "threshold", now, False, "timer")

    values = (
        "threshold:2026-W30:00001:60",
        "run-1",
        "00001",
        "manager@example.com",
        "threshold",
        60,
        now.isoformat(),
        now.isoformat(),
    )
    statement = (
        "INSERT INTO notification_attempts("
        "dedupe_key,run_id,employee_code,recipient,notification_type,"
        "threshold_percent,status,attempt_count,created_at,updated_at"
        ") VALUES(?,?,?,?,?,?,'pending',0,?,?)"
    )

    with db.transaction() as conn:
        conn.execute(statement, values)

    with pytest.raises(sqlite3.IntegrityError), db.transaction() as conn:
        conn.execute(statement, values)

    with db.connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM notification_attempts").fetchone()[0]
    assert count == 1


def test_transaction_rolls_back_on_error(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.initialize()

    with pytest.raises(RuntimeError), db.transaction() as conn:
        conn.execute("INSERT INTO schema_meta(key, value) VALUES('rollback-test', 'before-error')")
        raise RuntimeError("force rollback")

    with db.connect() as conn:
        row = conn.execute("SELECT value FROM schema_meta WHERE key='rollback-test'").fetchone()
    assert row is None


def test_database_initialization_creates_employee_schema_version_(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.initialize()

    with db.connect() as conn:
        version = conn.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='employees'"
        ).fetchone()

    assert version == "8"
    assert table["name"] == "employees"


def test_database_reports_initialization_state(tmp_path):
    db = Database(tmp_path / "test.sqlite3")

    assert db.is_initialized() is False

    db.initialize()

    assert db.is_initialized() is True


def test_database_initialization_adds_kot_sync_backup_path_to_existing_schema(tmp_path):
    path = tmp_path / "test.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO schema_meta(key, value) VALUES('schema_version', '3');
        CREATE TABLE kot_sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            executed_at TEXT NOT NULL,
            actor TEXT NOT NULL,
            fetched_count INTEGER NOT NULL,
            created_count INTEGER NOT NULL,
            updated_count INTEGER NOT NULL,
            disabled_count INTEGER NOT NULL,
            unchanged_count INTEGER NOT NULL,
            status TEXT NOT NULL,
            error_summary TEXT
        );
        """
    )
    conn.close()

    Database(path).initialize()

    with Database(path).connect() as migrated:
        columns = {row["name"] for row in migrated.execute("PRAGMA table_info(kot_sync_runs)")}
        version = migrated.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]

    assert "backup_path" in columns
    assert version == "8"


def test_database_initialization_adds_reactivated_count_and_schema_version_8(tmp_path):
    path = tmp_path / "test.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO schema_meta(key, value) VALUES('schema_version', '4');
        CREATE TABLE kot_sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            executed_at TEXT NOT NULL,
            actor TEXT NOT NULL,
            fetched_count INTEGER NOT NULL,
            created_count INTEGER NOT NULL,
            updated_count INTEGER NOT NULL,
            disabled_count INTEGER NOT NULL,
            unchanged_count INTEGER NOT NULL,
            status TEXT NOT NULL,
            error_summary TEXT,
            backup_path TEXT
        );
        INSERT INTO kot_sync_runs(
            executed_at, actor, fetched_count, created_count, updated_count,
            disabled_count, unchanged_count, status
        ) VALUES('2026-07-24T12:00:00+09:00', 'hiro', 1, 0, 0, 0, 1, 'succeeded');
        """
    )
    conn.close()

    Database(path).initialize()

    with Database(path).connect() as migrated:
        columns = {row["name"] for row in migrated.execute("PRAGMA table_info(kot_sync_runs)")}
        row = migrated.execute("SELECT reactivated_count FROM kot_sync_runs").fetchone()
        version = migrated.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]
    assert "reactivated_count" in columns
    assert row["reactivated_count"] == 0
    assert version == "8"


def test_database_migrates_execution_run_source_with_unknown_default(tmp_path):
    path = tmp_path / "test.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO schema_meta(key, value) VALUES('schema_version', '5');
            CREATE TABLE execution_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL UNIQUE,
                mode TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                dry_run INTEGER NOT NULL DEFAULT 0,
                error_message TEXT
            );
            INSERT INTO execution_runs(run_id, mode, started_at, status, dry_run)
            VALUES('legacy-run', 'weekly', '2026-07-24T21:30:00+09:00', 'succeeded', 0);
            """
        )

    db = Database(path)
    db.initialize()

    with db.connect_readonly() as conn:
        row = conn.execute("SELECT source FROM execution_runs WHERE run_id='legacy-run'").fetchone()
        version = conn.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
    assert row["source"] == "unknown"
    assert version["value"] == "8"


def test_start_run_records_execution_source(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.initialize()
    now = datetime(2026, 7, 25, 10, 30, tzinfo=ZoneInfo("Asia/Tokyo"))

    db.start_run("run-source", "threshold", now, False, "manual")

    with db.connect_readonly() as conn:
        row = conn.execute("SELECT source FROM execution_runs WHERE run_id='run-source'").fetchone()
    assert row["source"] == "manual"


def test_database_migrates_notification_attempts_for_duplicate_trace(tmp_path):
    path = tmp_path / "test.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO schema_meta(key, value) VALUES('schema_version', '6');
            CREATE TABLE execution_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL UNIQUE,
                mode TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                dry_run INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'unknown',
                error_message TEXT
            );
            INSERT INTO execution_runs(run_id, mode, started_at, status, dry_run, source)
            VALUES('legacy-run', 'weekly', '2026-07-24T21:30:00+09:00', 'succeeded', 0, 'timer');
            CREATE TABLE notification_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dedupe_key TEXT NOT NULL,
                run_id TEXT NOT NULL,
                employee_code TEXT,
                recipient TEXT NOT NULL,
                notification_type TEXT NOT NULL,
                threshold_percent INTEGER,
                status TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                slack_timestamp TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(dedupe_key, recipient)
            );
            INSERT INTO notification_attempts(
                dedupe_key, run_id, employee_code, recipient, notification_type,
                status, attempt_count, created_at, updated_at
            ) VALUES(
                'weekly:2026-W30:00001', 'legacy-run', '00001', 'manager@example.com',
                'weekly', 'sent', 1, '2026-07-24T21:30:00+09:00',
                '2026-07-24T21:30:01+09:00'
            );
            """
        )

    db = Database(path)
    db.initialize()

    with db.connect_readonly() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(notification_attempts)")}
        version = conn.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]
        row = conn.execute(
            "SELECT status, duplicate_of_attempt_id FROM notification_attempts"
        ).fetchone()
    assert "duplicate_of_attempt_id" in columns
    assert version == "8"
    assert row["status"] == "sent"
    assert row["duplicate_of_attempt_id"] is None
