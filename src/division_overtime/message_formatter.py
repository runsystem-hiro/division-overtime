from __future__ import annotations

from .models import OvertimeSnapshot

REPORT_TITLE = "残業時間レポート"
REPORT_SEPARATOR = "=" * 29


def format_minutes(minutes: int) -> str:
    """Convert a minute count to the legacy H:MM display format."""
    return f"{minutes // 60}:{minutes % 60:02d}"


def status_message(percent_target: int) -> str:
    """Return the status label used by the legacy Slack notifications."""
    if percent_target >= 100:
        return "🚨 目安100%超過"
    if percent_target >= 90:
        return "⚠️ 警告:90%超過"
    if percent_target >= 80:
        return "⚠️ 注意:80%超過"
    if percent_target >= 70:
        return "📙 注意: 70%超過"
    if percent_target >= 60:
        return "📗 備考: 60%超過"
    if percent_target >= 50:
        return "📘 備考: 50%超過"
    return "✅ 問題なし"


def format_employee_report(snapshot: OvertimeSnapshot) -> str:
    """Format one employee report with the legacy wording and layout."""
    remaining_minutes = snapshot.target_minutes - snapshot.current_minutes

    line1 = f"👤 {snapshot.employee.full_name} {status_message(snapshot.target_percent)}"
    line2 = f"🗓️ 今月({snapshot.target_month}) 残業 {format_minutes(snapshot.current_minutes)}"

    if snapshot.target_minutes == 0:
        if snapshot.current_minutes > 0:
            line3 = f"📊 目安0分設定 🔥 残業発生: +{format_minutes(snapshot.current_minutes)}"
        else:
            line3 = "📊 目安0分設定 ✅ 残業なし"
    elif remaining_minutes < 0:
        line3 = (
            f"📊 目安比 {snapshot.target_percent}％ 🔥 目安超過: "
            f"+{format_minutes(abs(remaining_minutes))}"
        )
    else:
        line3 = (
            f"📊 目安比 {snapshot.target_percent}％ ⌛ 目安まで {format_minutes(remaining_minutes)}"
        )

    line4 = (
        f"🔙 前月残業 {format_minutes(snapshot.previous_minutes)} "
        f"前月比 {snapshot.previous_percent}%"
    )
    return "\n".join((line1, line2, line3, line4))


def format_department_message(snapshots: list[OvertimeSnapshot]) -> str:
    reports = "\n\n".join(format_employee_report(snapshot) for snapshot in snapshots)
    return f"{REPORT_TITLE}\n{REPORT_SEPARATOR}\n\n{reports}"


def format_self_message(snapshot: OvertimeSnapshot) -> str:
    return (
        f"{snapshot.employee.full_name}さんの残業状況レポート\n\n{format_employee_report(snapshot)}"
    )
