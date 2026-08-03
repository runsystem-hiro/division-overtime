from datetime import datetime, timedelta
from pathlib import Path

import pytest

from division_overtime.backup_retention import prune_backup_directories


def _create_generation(root: Path, when: datetime, *, filename: str = "database.sqlite3") -> Path:
    generation = root / when.strftime("%Y%m%d_%H%M%S_%f")
    generation.mkdir(parents=True)
    (generation / filename).write_text("backup", encoding="utf-8")
    return generation


def test_prune_backup_directories_keeps_latest_thirty(tmp_path: Path) -> None:
    root = tmp_path / "deploy-database"
    start = datetime(2026, 7, 1, 0, 0)
    generations = [_create_generation(root, start + timedelta(hours=i)) for i in range(31)]

    result = prune_backup_directories(root, required_filenames=frozenset({"database.sqlite3"}))

    assert result.removed_count == 1
    assert result.retained_count == 30
    assert generations[0].exists() is False
    assert all(path.exists() for path in generations[1:])


def test_prune_backup_directories_ignores_unmanaged_incomplete_and_symlink(
    tmp_path: Path,
) -> None:
    root = tmp_path / "deploy-database"
    root.mkdir()
    unmanaged = root / "manual-note"
    unmanaged.mkdir()
    incomplete = root / "20260701_000000_000000"
    incomplete.mkdir()
    target = tmp_path / "outside"
    target.mkdir()
    (target / "database.sqlite3").write_text("outside", encoding="utf-8")
    link = root / "20260701_000001_000000"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symlinks are not available")

    result = prune_backup_directories(
        root, required_filenames=frozenset({"database.sqlite3"}), retention=1
    )

    assert result.removed_count == 0
    assert unmanaged.exists()
    assert incomplete.exists()
    assert link.exists()
    assert (target / "database.sqlite3").exists()


def test_prune_backup_directories_rejects_symlink_root(tmp_path: Path) -> None:
    target = tmp_path / "actual"
    target.mkdir()
    link = tmp_path / "linked"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symlinks are not available")

    with pytest.raises(ValueError, match="regular directory"):
        prune_backup_directories(link, required_filenames=frozenset({"database.sqlite3"}))
