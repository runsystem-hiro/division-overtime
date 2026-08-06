from __future__ import annotations

from division_overtime.king_of_time import KingOfTimeClient, MonthlyOvertime


def test_normalize_preserves_total_and_night_overtime():
    result = KingOfTimeClient._normalize(
        [
            {
                "employeeKey": "test-employee-key",
                "overtime": 345,
                "nightOvertime": 195,
            }
        ]
    )

    assert result == {
        "test-employee-key": MonthlyOvertime(
            total_minutes=540,
            night_overtime_minutes=195,
        )
    }


def test_normalize_treats_missing_or_null_night_overtime_as_zero():
    result = KingOfTimeClient._normalize(
        [
            {"employeeKey": "missing-night", "overtime": 60},
            {
                "employeeKey": "null-night",
                "overtime": 120,
                "nightOvertime": None,
            },
        ]
    )

    assert result == {
        "missing-night": MonthlyOvertime(60, 0),
        "null-night": MonthlyOvertime(120, 0),
    }
