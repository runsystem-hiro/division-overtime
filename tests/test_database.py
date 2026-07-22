import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from division_overtime.database import Database


def test_database_initialization(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.initialize()
    assert db.integrity_check() == "ok"


def test_notification_unique_constraint_prevents_duplicate(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.initialize()
    now = datetime(2026, 7, 22, 10, 30, tzinfo=ZoneInfo("Asia/Tokyo"))
    db.start_run("run-1", "threshold", now, False)

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
