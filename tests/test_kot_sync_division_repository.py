from pathlib import Path

import pytest

from division_overtime.database import Database
from division_overtime.kot_sync_division_repository import (
    KotSyncDivisionError,
    KotSyncDivisionRepository,
)


def test_seed_and_manage_kot_sync_divisions(tmp_path: Path) -> None:
    database = Database(tmp_path / "division.sqlite3")
    database.initialize()
    repository = KotSyncDivisionRepository(database)

    repository.seed_if_empty(("156", "158", "156"))
    assert repository.list_enabled_codes() == ("156", "158")

    created = repository.create("300")
    assert created.division_code == "300"
    assert created.is_enabled is True

    disabled = repository.set_enabled("158", False)
    assert disabled.is_enabled is False
    assert repository.list_enabled_codes() == ("156", "300")

    deleted = repository.delete("158")
    assert deleted.division_code == "158"
    assert [item.division_code for item in repository.list_all()] == ["156", "300"]


def test_last_enabled_division_cannot_be_disabled_or_deleted(tmp_path: Path) -> None:
    database = Database(tmp_path / "division.sqlite3")
    database.initialize()
    repository = KotSyncDivisionRepository(database)
    repository.seed_if_empty(("156",))

    with pytest.raises(KotSyncDivisionError, match="At least one enabled"):
        repository.set_enabled("156", False)

    with pytest.raises(KotSyncDivisionError, match="At least one enabled"):
        repository.delete("156")
