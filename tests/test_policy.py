import pytest

from division_overtime.models import Employee, OvertimeSnapshot
from division_overtime.policy import notification_dedupe_key, reached_threshold, target_minutes


def employee(personal=None):
    return Employee(
        "00001",
        "key",
        "田中",
        "太郎",
        "t@example.com",
        "300",
        personal_target_minutes=personal,
    )


def test_target_priority():
    assert target_minutes(employee(1200), {"300": 600}, 300) == 1200
    assert target_minutes(employee(), {"300": 600}, 300) == 600
    assert target_minutes(Employee("2", "k", "A", "B", "", "999"), {}, 300) == 300


@pytest.mark.parametrize(
    ("percent", "expected"),
    [
        (0, None),
        (59, None),
        (60, 60),
        (69, 60),
        (70, 70),
        (79, 70),
        (80, 80),
        (89, 80),
        (90, 90),
        (99, 90),
        (100, 100),
        (125, 100),
    ],
)
def test_threshold_boundaries(percent, expected):
    assert reached_threshold(percent, (60, 70, 80, 90, 100)) == expected


def test_weekly_dedupe_key():
    snapshot = OvertimeSnapshot(employee(), "2026-07", 100, 50, 600)
    assert notification_dedupe_key(snapshot, "weekly", None, 2026, 30) == ("weekly:2026-W30:00001")


def test_threshold_dedupe_key_includes_threshold():
    snapshot = OvertimeSnapshot(employee(), "2026-07", 360, 300, 600)
    assert notification_dedupe_key(snapshot, "threshold", 60, 2026, 30) == (
        "threshold:2026-W30:00001:60"
    )
