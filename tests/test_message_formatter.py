from __future__ import annotations

import pytest

from division_overtime.message_formatter import (
    format_department_message,
    format_employee_report,
    format_self_message,
    status_message,
)
from division_overtime.models import Employee, OvertimeSnapshot


def make_snapshot(
    *,
    current: int,
    previous: int = 300,
    target: int = 600,
    name: tuple[str, str] = ("田中", "太郎"),
) -> OvertimeSnapshot:
    return OvertimeSnapshot(
        employee=Employee(
            code="00001",
            employee_key="employee-key-1",
            last_name=name[0],
            first_name=name[1],
            email="tanaka@example.com",
            division_code="300",
            division_name="営業部",
        ),
        target_month="2026-07",
        current_minutes=current,
        previous_minutes=previous,
        target_minutes=target,
    )


@pytest.mark.parametrize(
    ("percent", "expected"),
    [
        (0, "✅ 問題なし"),
        (49, "✅ 問題なし"),
        (50, "📘 備考: 50%超過"),
        (59, "📘 備考: 50%超過"),
        (60, "📗 備考: 60%超過"),
        (69, "📗 備考: 60%超過"),
        (70, "📙 注意: 70%超過"),
        (79, "📙 注意: 70%超過"),
        (80, "⚠️ 注意:80%超過"),
        (89, "⚠️ 注意:80%超過"),
        (90, "⚠️ 警告:90%超過"),
        (99, "⚠️ 警告:90%超過"),
        (100, "🚨 目安100%超過"),
        (125, "🚨 目安100%超過"),
    ],
)
def test_status_message_uses_legacy_thresholds(percent: int, expected: str):
    assert status_message(percent) == expected


def test_format_employee_report_below_target_matches_legacy_style():
    snapshot = make_snapshot(current=450, previous=360, target=600)

    assert format_employee_report(snapshot) == "\n".join(
        [
            "👤 田中太郎 📙 注意: 70%超過",
            "🗓️ 今月(2026-07) 残業 7:30",
            "📊 目安比 75％ ⌛ 目安まで 2:30",
            "🔙 前月残業 6:00 前月比 125%",
        ]
    )


def test_format_employee_report_over_target_matches_legacy_style():
    snapshot = make_snapshot(current=660, previous=600, target=600)

    assert format_employee_report(snapshot) == "\n".join(
        [
            "👤 田中太郎 🚨 目安100%超過",
            "🗓️ 今月(2026-07) 残業 11:00",
            "📊 目安比 110％ 🔥 目安超過: +1:00",
            "🔙 前月残業 10:00 前月比 110%",
        ]
    )


def test_format_employee_report_zero_target_with_overtime_matches_legacy_style():
    snapshot = make_snapshot(current=45, previous=30, target=0, name=("吉田", "麻優"))

    assert format_employee_report(snapshot) == "\n".join(
        [
            "👤 吉田麻優 🚨 目安100%超過",
            "🗓️ 今月(2026-07) 残業 0:45",
            "📊 目安0分設定 🔥 残業発生: +0:45",
            "🔙 前月残業 0:30 前月比 150%",
        ]
    )


def test_format_employee_report_zero_target_without_overtime_matches_legacy_style():
    snapshot = make_snapshot(current=0, previous=0, target=0)

    assert format_employee_report(snapshot) == "\n".join(
        [
            "👤 田中太郎 ✅ 問題なし",
            "🗓️ 今月(2026-07) 残業 0:00",
            "📊 目安0分設定 ✅ 残業なし",
            "🔙 前月残業 0:00 前月比 0%",
        ]
    )


def test_department_message_uses_legacy_header_and_blank_lines():
    first = make_snapshot(current=360)
    second = make_snapshot(current=420, name=("佐藤", "花子"))

    message = format_department_message([first, second])

    assert message.startswith("残業時間レポート\n=============================\n\n")
    assert "\n\n👤 佐藤花子 📙 注意: 70%超過\n" in message


def test_self_message_uses_legacy_personal_header():
    snapshot = make_snapshot(current=360)

    assert format_self_message(snapshot).startswith(
        "田中太郎さんの残業状況レポート\n\n👤 田中太郎 📗 備考: 60%超過"
    )
