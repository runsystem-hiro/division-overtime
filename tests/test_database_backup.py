from pathlib import Path

from division_overtime.database import Database


def test_backup_to_removes_sqlite_sidecars(tmp_path: Path) -> None:
    source = Database(tmp_path / "source.sqlite3")
    source.initialize()

    destination = tmp_path / "backup" / "division_overtime.sqlite3"
    destination.parent.mkdir(parents=True)
    destination.with_name(f"{destination.name}-wal").write_bytes(b"stale-wal")
    destination.with_name(f"{destination.name}-shm").write_bytes(b"stale-shm")

    source.backup_to(destination)

    assert destination.exists()
    assert not destination.with_name(f"{destination.name}-wal").exists()
    assert not destination.with_name(f"{destination.name}-shm").exists()

    with Database(destination).connect() as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_backup_to_allows_missing_sidecars(tmp_path: Path) -> None:
    source = Database(tmp_path / "source.sqlite3")
    source.initialize()

    destination = tmp_path / "backup" / "division_overtime.sqlite3"

    source.backup_to(destination)

    assert destination.exists()
    assert not destination.with_name(f"{destination.name}-wal").exists()
    assert not destination.with_name(f"{destination.name}-shm").exists()
