from __future__ import annotations

from .models import Employee, OvertimeSnapshot


def target_minutes(employee: Employee, division_targets: dict[str, int], default: int) -> int:
    if employee.personal_target_minutes is not None:
        return employee.personal_target_minutes
    return division_targets.get(employee.division_code, default)


def reached_threshold(percent: int, thresholds: tuple[int, ...]) -> int | None:
    reached = [threshold for threshold in thresholds if percent >= threshold]
    return max(reached) if reached else None


def notification_dedupe_key(
    snapshot: OvertimeSnapshot,
    mode: str,
    threshold: int | None,
    iso_year: int,
    iso_week: int,
) -> str:
    if mode == "weekly":
        return f"weekly:{iso_year}-W{iso_week:02d}:{snapshot.employee.code}"
    return f"threshold:{iso_year}-W{iso_week:02d}:{snapshot.employee.code}:{threshold}"
