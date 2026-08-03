from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .backup_retention import (
    AUTOMATIC_BACKUP_RETENTION,
    BACKUP_DIRECTORY_TIMESTAMP_FORMAT,
)

_EMPLOYEE_CSV_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S%f"


@dataclass(frozen=True, slots=True)
class BackupObservation:
    name: str
    count: int
    retention: int
    latest: str | None
    ignored_count: int
    status: str


@dataclass(frozen=True, slots=True)
class _BackupGeneration:
    timestamp: datetime
    identifier: str


def observe_automatic_backups(
    *,
    database_path: Path,
    employee_csv: Path,
    retention: int = AUTOMATIC_BACKUP_RETENTION,
) -> tuple[BackupObservation, ...]:
    backup_root = database_path.parent / "backups"
    return (
        _observe_directory_generations(
            "deploy_database",
            backup_root / "deploy-database",
            retention=retention,
            validator=lambda path: _has_regular_files(path, {database_path.name}),
        ),
        _observe_directory_generations(
            "employee_delete",
            backup_root / "employee-delete",
            retention=retention,
            validator=lambda path: _has_regular_files(
                path, {database_path.name, employee_csv.name}
            ),
        ),
        _observe_employee_csv_backups(
            employee_csv.parent / "backups" / "employee-csv",
            employee_csv,
            retention=retention,
        ),
        _observe_directory_generations(
            "kot_sync",
            backup_root / "kot-sync",
            retention=retention,
            validator=lambda _path: True,
        ),
    )


def _observe_directory_generations(
    name: str,
    backup_root: Path,
    *,
    retention: int,
    validator: Callable[[Path], bool],
) -> BackupObservation:
    generations: list[_BackupGeneration] = []
    ignored_count = 0

    if backup_root.exists():
        if backup_root.is_symlink() or not backup_root.is_dir():
            return _observation(name, [], retention, ignored_count=1)
        resolved_root = backup_root.resolve(strict=True)
        for candidate in backup_root.iterdir():
            if candidate.is_symlink() or not candidate.is_dir():
                ignored_count += 1
                continue
            try:
                timestamp = datetime.strptime(candidate.name, BACKUP_DIRECTORY_TIMESTAMP_FORMAT)
            except ValueError:
                ignored_count += 1
                continue
            if candidate.parent.resolve(strict=True) != resolved_root or not validator(candidate):
                ignored_count += 1
                continue
            generations.append(_BackupGeneration(timestamp, candidate.name))

    return _observation(name, generations, retention, ignored_count=ignored_count)


def _observe_employee_csv_backups(
    backup_root: Path,
    source_path: Path,
    *,
    retention: int,
) -> BackupObservation:
    generations: list[_BackupGeneration] = []
    ignored_count = 0
    pattern = re.compile(
        rf"^{re.escape(source_path.stem)}_(\d{{8}}_\d{{12}}){re.escape(source_path.suffix)}$"
    )

    if backup_root.exists():
        if backup_root.is_symlink() or not backup_root.is_dir():
            return _observation("employee_csv", [], retention, ignored_count=1)
        resolved_root = backup_root.resolve(strict=True)
        for candidate in backup_root.iterdir():
            if candidate.is_symlink() or not candidate.is_file():
                ignored_count += 1
                continue
            if candidate.parent.resolve(strict=True) != resolved_root:
                ignored_count += 1
                continue
            match = pattern.fullmatch(candidate.name)
            if match is None:
                ignored_count += 1
                continue
            try:
                timestamp = datetime.strptime(match.group(1), _EMPLOYEE_CSV_TIMESTAMP_FORMAT)
            except ValueError:
                ignored_count += 1
                continue
            generations.append(_BackupGeneration(timestamp, match.group(1)))

    return _observation("employee_csv", generations, retention, ignored_count=ignored_count)


def _has_regular_files(directory: Path, filenames: set[str]) -> bool:
    return all(
        (directory / filename).exists()
        and not (directory / filename).is_symlink()
        and (directory / filename).is_file()
        for filename in filenames
    )


def _observation(
    name: str,
    generations: list[_BackupGeneration],
    retention: int,
    *,
    ignored_count: int,
) -> BackupObservation:
    ordered = sorted(generations, key=lambda item: (item.timestamp, item.identifier))
    latest = ordered[-1].identifier if ordered else None
    status = "warning" if len(ordered) > retention or ignored_count else "ok"
    return BackupObservation(
        name=name,
        count=len(ordered),
        retention=retention,
        latest=latest,
        ignored_count=ignored_count,
        status=status,
    )
