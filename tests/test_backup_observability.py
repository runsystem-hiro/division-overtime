from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from division_overtime.backup_observability import observe_automatic_backups


def _generation(root: Path, timestamp: datetime, *filenames: str) -> Path:
    path = root / timestamp.strftime("%Y%m%d_%H%M%S_%f")
    path.mkdir(parents=True)
    for filename in filenames:
        (path / filename).write_text("backup", encoding="utf-8")
    return path


def test_observe_automatic_backups_reports_all_categories(tmp_path: Path) -> None:
    database_path = tmp_path / "var" / "division_overtime.sqlite3"
    employee_csv = tmp_path / "data" / "employeeKey.csv"
    now = datetime(2026, 8, 3, 17, 15, 55, 367173)

    _generation(
        database_path.parent / "backups" / "deploy-database",
        now,
        database_path.name,
    )
    _generation(
        database_path.parent / "backups" / "employee-delete",
        now - timedelta(hours=1),
        database_path.name,
        employee_csv.name,
    )
    csv_root = employee_csv.parent / "backups" / "employee-csv"
    csv_root.mkdir(parents=True)
    (csv_root / "employeeKey_20260803_161555367173.csv").write_text("backup", encoding="utf-8")
    _generation(database_path.parent / "backups" / "kot-sync", now - timedelta(days=1))

    observations = {
        item.name: item
        for item in observe_automatic_backups(
            database_path=database_path, employee_csv=employee_csv
        )
    }

    assert set(observations) == {
        "deploy_database",
        "employee_delete",
        "employee_csv",
        "kot_sync",
    }
    assert observations["deploy_database"].count == 1
    assert observations["deploy_database"].latest == "20260803_171555_367173"
    assert observations["employee_delete"].count == 1
    assert observations["employee_csv"].count == 1
    assert observations["employee_csv"].latest == "20260803_161555367173"
    assert observations["kot_sync"].count == 1
    assert all(item.retention == 30 for item in observations.values())
    assert all(item.status == "ok" for item in observations.values())


def test_observe_automatic_backups_reports_zero_for_missing_roots(tmp_path: Path) -> None:
    observations = observe_automatic_backups(
        database_path=tmp_path / "var" / "division_overtime.sqlite3",
        employee_csv=tmp_path / "data" / "employeeKey.csv",
    )

    assert all(item.count == 0 for item in observations)
    assert all(item.latest is None for item in observations)
    assert all(item.ignored_count == 0 for item in observations)
    assert all(item.status == "ok" for item in observations)


def test_observe_automatic_backups_warns_for_ignored_and_excess_generations(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "var" / "division_overtime.sqlite3"
    employee_csv = tmp_path / "data" / "employeeKey.csv"
    deploy_root = database_path.parent / "backups" / "deploy-database"
    start = datetime(2026, 7, 1)
    for index in range(31):
        _generation(deploy_root, start + timedelta(hours=index), database_path.name)
    (deploy_root / "manual-keep").mkdir()
    incomplete = deploy_root / "20260803_000000_000000"
    incomplete.mkdir()

    observation = observe_automatic_backups(database_path=database_path, employee_csv=employee_csv)[
        0
    ]

    assert observation.count == 31
    assert observation.ignored_count == 2
    assert observation.status == "warning"


def test_observe_automatic_backups_does_not_follow_symlinks(tmp_path: Path) -> None:
    database_path = tmp_path / "var" / "division_overtime.sqlite3"
    employee_csv = tmp_path / "data" / "employeeKey.csv"
    deploy_root = database_path.parent / "backups" / "deploy-database"
    deploy_root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / database_path.name).write_text("secret", encoding="utf-8")
    link = deploy_root / "20260803_000000_000000"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        return

    observation = observe_automatic_backups(database_path=database_path, employee_csv=employee_csv)[
        0
    ]

    assert observation.count == 0
    assert observation.ignored_count == 1
    assert observation.status == "warning"
