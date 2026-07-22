from division_overtime.models import Employee, OvertimeSnapshot
from division_overtime.policy import notification_dedupe_key, reached_threshold, target_minutes


def employee(personal=None):
    return Employee(
        "00001", "key", "田中", "太郎", "t@example.com", "300", personal_target_minutes=personal
    )


def test_target_priority():
    assert target_minutes(employee(1200), {"300": 600}, 300) == 1200
    assert target_minutes(employee(), {"300": 600}, 300) == 600
    assert target_minutes(Employee("2", "k", "A", "B", "", "999"), {}, 300) == 300


def test_threshold_returns_highest_reached():
    assert reached_threshold(89, (60, 70, 80, 90, 100)) == 80
    assert reached_threshold(59, (60, 70, 80, 90, 100)) is None


def test_weekly_dedupe_key():
    snapshot = OvertimeSnapshot(employee(), "2026-07", 100, 50, 600)
    assert notification_dedupe_key(snapshot, "weekly", None, 2026, 30) == "weekly:2026-W30:00001"
