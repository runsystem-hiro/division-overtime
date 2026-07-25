from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .database import Database

_TRACKED_TABLES = (
    "execution_runs",
    "notification_attempts",
    "employees",
    "kot_sync_runs",
)


@dataclass(frozen=True, slots=True)
class DatabaseObservation:
    database_path: Path
    database_bytes: int
    wal_bytes: int
    shm_bytes: int
    total_bytes: int
    table_counts: dict[str, int]
    notification_attempt_counts: dict[str, int]
    integrity_check: str


def observe_database(database: Database) -> DatabaseObservation:
    if not database.is_initialized_readonly():
        raise RuntimeError(f"Database is not initialized: {database.path}")

    database_path = database.path
    wal_path = database_path.with_name(f"{database_path.name}-wal")
    shm_path = database_path.with_name(f"{database_path.name}-shm")

    with database.connect_readonly() as conn:
        table_counts = {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in _TRACKED_TABLES
        }
        attempt_counts = {
            str(row["status"]): int(row["count"])
            for row in conn.execute(
                "SELECT status, COUNT(*) AS count "
                "FROM notification_attempts GROUP BY status ORDER BY status"
            )
        }
        integrity_check = str(conn.execute("PRAGMA integrity_check").fetchone()[0])

    database_bytes = _file_size(database_path)
    wal_bytes = _file_size(wal_path)
    shm_bytes = _file_size(shm_path)
    return DatabaseObservation(
        database_path=database_path,
        database_bytes=database_bytes,
        wal_bytes=wal_bytes,
        shm_bytes=shm_bytes,
        total_bytes=database_bytes + wal_bytes + shm_bytes,
        table_counts=table_counts,
        notification_attempt_counts=attempt_counts,
        integrity_check=integrity_check,
    )


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0
