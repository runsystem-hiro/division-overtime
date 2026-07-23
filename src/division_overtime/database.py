from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = 3


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.transaction() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS execution_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL UNIQUE,
                    mode TEXT NOT NULL CHECK(mode IN ('threshold','weekly','health')),
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL CHECK(status IN ('running','succeeded','failed')),
                    dry_run INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT
                );
                CREATE TABLE IF NOT EXISTS overtime_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    target_month TEXT NOT NULL,
                    employee_code TEXT NOT NULL,
                    employee_name TEXT NOT NULL,
                    division_code TEXT NOT NULL,
                    current_minutes INTEGER NOT NULL,
                    previous_minutes INTEGER NOT NULL,
                    target_minutes INTEGER NOT NULL,
                    target_percent INTEGER NOT NULL,
                    captured_at TEXT NOT NULL,
                    UNIQUE(run_id, employee_code),
                    FOREIGN KEY(run_id) REFERENCES execution_runs(run_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS notification_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dedupe_key TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    employee_code TEXT,
                    recipient TEXT NOT NULL,
                    notification_type TEXT NOT NULL,
                    threshold_percent INTEGER,
                    status TEXT NOT NULL CHECK(status IN ('pending','sent','failed','skipped')),
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    slack_timestamp TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(dedupe_key, recipient),
                    FOREIGN KEY(run_id) REFERENCES execution_runs(run_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_notification_status
                    ON notification_attempts(status, updated_at);
                CREATE TABLE IF NOT EXISTS employees (
                    code TEXT PRIMARY KEY,
                    kot_key TEXT NOT NULL,
                    last_name TEXT NOT NULL,
                    first_name TEXT NOT NULL,
                    division_code TEXT NOT NULL,
                    division_name TEXT NOT NULL DEFAULT '',
                    email TEXT,
                    personal_target_minutes INTEGER
                        CHECK(personal_target_minutes IS NULL OR personal_target_minutes >= 0),
                    is_enabled INTEGER NOT NULL DEFAULT 1 CHECK(is_enabled IN (0, 1)),
                    disabled_reason TEXT,
                    note TEXT,
                    kot_group_codes TEXT,
                    kot_group_names TEXT,
                    kot_exists INTEGER NOT NULL DEFAULT 1 CHECK(kot_exists IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_synced_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_employees_division
                    ON employees(division_code, is_enabled);
                CREATE TABLE IF NOT EXISTS kot_sync_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    executed_at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    fetched_count INTEGER NOT NULL,
                    created_count INTEGER NOT NULL,
                    updated_count INTEGER NOT NULL,
                    disabled_count INTEGER NOT NULL,
                    unchanged_count INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('succeeded','failed')),
                    error_summary TEXT
                );
                """
            )
            current_row = conn.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()
            current_version = int(current_row["value"]) if current_row else 0
            if current_version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema version {current_version} is newer than "
                    f"supported version {SCHEMA_VERSION}"
                )
            conn.execute(
                "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )

    def is_initialized(self) -> bool:
        if not self.path.exists():
            return False
        with self.connect() as conn:
            table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_meta'"
            ).fetchone()
            if table is None:
                return False
            version = conn.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()
            employees = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='employees'"
            ).fetchone()
        return (
            version is not None
            and int(version["value"]) == SCHEMA_VERSION
            and employees is not None
        )

    def integrity_check(self) -> str:
        with self.connect() as conn:
            return str(conn.execute("PRAGMA integrity_check").fetchone()[0])

    def start_run(self, run_id: str, mode: str, started_at: datetime, dry_run: bool) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO execution_runs(run_id, mode, started_at, status, dry_run) "
                "VALUES(?, ?, ?, 'running', ?)",
                (run_id, mode, started_at.isoformat(), int(dry_run)),
            )

    def finish_run(
        self, run_id: str, finished_at: datetime, status: str, error: str | None = None
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE execution_runs SET finished_at=?, status=?, error_message=? WHERE run_id=?",
                (finished_at.isoformat(), status, error, run_id),
            )
