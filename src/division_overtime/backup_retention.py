from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

AUTOMATIC_BACKUP_RETENTION = 30
BACKUP_DIRECTORY_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S_%f"


@dataclass(frozen=True, slots=True)
class BackupPruneResult:
    removed_count: int
    retained_count: int


def prune_backup_directories(
    backup_root: Path,
    *,
    required_filenames: frozenset[str],
    retention: int = AUTOMATIC_BACKUP_RETENTION,
) -> BackupPruneResult:
    """Remove only recognized old backup directories directly under an allowed root."""
    if retention < 1:
        raise ValueError("Backup retention must be at least 1")
    if not required_filenames or any(Path(name).name != name for name in required_filenames):
        raise ValueError("Required backup filenames must be plain filenames")
    if not backup_root.exists():
        return BackupPruneResult(removed_count=0, retained_count=0)
    if backup_root.is_symlink() or not backup_root.is_dir():
        raise ValueError(f"Backup root must be a regular directory: {backup_root}")

    resolved_root = backup_root.resolve(strict=True)
    candidates: list[tuple[datetime, Path]] = []
    for candidate in backup_root.iterdir():
        if candidate.is_symlink() or not candidate.is_dir():
            continue
        try:
            timestamp = datetime.strptime(candidate.name, BACKUP_DIRECTORY_TIMESTAMP_FORMAT)
        except ValueError:
            continue
        if candidate.parent.resolve(strict=True) != resolved_root:
            continue
        if not all(_is_regular_direct_child(candidate, name) for name in required_filenames):
            continue
        candidates.append((timestamp, candidate))

    candidates.sort(key=lambda item: (item[0], item[1].name), reverse=True)
    stale = candidates[retention:]
    removed_count = 0
    for _, candidate in stale:
        try:
            if candidate.is_symlink() or candidate.parent.resolve(strict=True) != resolved_root:
                logger.warning("backup_prune=skipped unsafe_path=%s", candidate)
                continue
            shutil.rmtree(candidate)
            removed_count += 1
            logger.info("backup_prune=removed path=%s", candidate)
        except OSError:
            logger.warning("backup_prune=failed path=%s", candidate, exc_info=True)

    return BackupPruneResult(
        removed_count=removed_count,
        retained_count=len(candidates) - removed_count,
    )


def _is_regular_direct_child(directory: Path, filename: str) -> bool:
    candidate = directory / filename
    return candidate.exists() and not candidate.is_symlink() and candidate.is_file()
