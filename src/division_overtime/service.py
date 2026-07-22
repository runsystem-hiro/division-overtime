from __future__ import annotations

import logging
import sqlite3
import uuid
from collections import defaultdict
from datetime import datetime, timedelta

import jpholiday

from .config import AppConfig
from .database import Database
from .employees import load_employees
from .king_of_time import KingOfTimeClient
from .models import OvertimeSnapshot
from .policy import notification_dedupe_key, reached_threshold, target_minutes
from .slack import SlackDeliveryError, SlackMessenger

logger = logging.getLogger(__name__)


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60}:{minutes % 60:02d}"


def _report(snapshot: OvertimeSnapshot) -> str:
    remaining = snapshot.target_minutes - snapshot.current_minutes
    if snapshot.target_minutes == 0:
        target_line = (
            "目安0分 / 残業なし"
            if snapshot.current_minutes == 0
            else f"目安0分 / 超過 +{_hhmm(snapshot.current_minutes)}"
        )
    elif remaining < 0:
        target_line = f"目安比 {snapshot.target_percent}% / 超過 +{_hhmm(abs(remaining))}"
    else:
        target_line = f"目安比 {snapshot.target_percent}% / 残り {_hhmm(remaining)}"
    return "\n".join(
        [
            f"👤 {snapshot.employee.full_name}",
            f"🗓️ 今月残業 {_hhmm(snapshot.current_minutes)}",
            f"📊 {target_line}",
            f"🔙 前月残業 {_hhmm(snapshot.previous_minutes)} / 前月比 {snapshot.previous_percent}%",
        ]
    )


def run(config: AppConfig, mode: str, dry_run: bool = False) -> int:
    if mode not in {"threshold", "weekly"}:
        raise ValueError(f"Unsupported mode: {mode}")
    now = datetime.now(config.timezone)
    run_id = str(uuid.uuid4())
    db = Database(config.database_path)
    db.initialize()
    db.start_run(run_id, mode, now, dry_run)
    try:
        if mode == "threshold" and jpholiday.is_holiday(now.date()):
            logger.info("Japanese public holiday: threshold notification skipped")
            db.finish_run(run_id, datetime.now(config.timezone), "succeeded")
            return 0
        employees = load_employees(config.employee_csv)
        client = KingOfTimeClient(
            config.kot_base_url,
            config.kot_endpoint,
            config.kot_token,
            config.connect_timeout,
            config.read_timeout,
            config.retry_count,
            config.retry_backoff,
        )
        messenger = SlackMessenger(config.slack_token)
        current_month = now.strftime("%Y-%m")
        previous_month = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        division_codes = sorted({employee.division_code for employee in employees})
        current_by_division = {
            division: client.fetch_division_month(current_month, division)
            for division in division_codes
        }
        previous_by_division = {
            division: client.fetch_division_month(previous_month, division)
            for division in division_codes
        }

        reports_by_recipient: dict[str, list[tuple[OvertimeSnapshot, int | None, str]]] = (
            defaultdict(list)
        )
        with db.transaction() as conn:
            for employee in employees:
                snapshot = OvertimeSnapshot(
                    employee=employee,
                    target_month=current_month,
                    current_minutes=current_by_division[employee.division_code].get(
                        employee.employee_key, 0
                    ),
                    previous_minutes=previous_by_division[employee.division_code].get(
                        employee.employee_key, 0
                    ),
                    target_minutes=target_minutes(
                        employee, config.division_targets, config.default_target_minutes
                    ),
                )
                conn.execute(
                    "INSERT INTO overtime_snapshots("
                    "run_id,target_month,employee_code,employee_name,division_code,"
                    "current_minutes,previous_minutes,target_minutes,target_percent,captured_at"
                    ") VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        current_month,
                        employee.code,
                        employee.full_name,
                        employee.division_code,
                        snapshot.current_minutes,
                        snapshot.previous_minutes,
                        snapshot.target_minutes,
                        snapshot.target_percent,
                        now.isoformat(),
                    ),
                )
                threshold = (
                    None
                    if mode == "weekly"
                    else reached_threshold(snapshot.target_percent, config.thresholds)
                )
                if mode == "threshold" and threshold is None:
                    continue
                dedupe = notification_dedupe_key(snapshot, mode, threshold, *now.isocalendar()[:2])
                recipients = set(config.department_recipients.get("ALL", ()))
                recipients.update(config.department_recipients.get(employee.division_code, ()))
                for recipient in recipients:
                    reports_by_recipient[recipient].append((snapshot, threshold, dedupe))
                if (
                    config.enable_self_notify
                    and employee.email
                    and (
                        employee.code in config.self_notify_employee_codes
                        or snapshot.target_percent >= config.force_self_threshold
                        or mode == "weekly"
                    )
                ):
                    reports_by_recipient[employee.email].append(
                        (snapshot, threshold, dedupe + ":self")
                    )

        failed = 0
        for recipient, items in reports_by_recipient.items():
            sendable: list[tuple[OvertimeSnapshot, int | None, str]] = []
            if dry_run:
                sendable = items
            else:
                with db.transaction() as conn:
                    for snapshot, threshold, dedupe in items:
                        try:
                            conn.execute(
                                "INSERT INTO notification_attempts("
                                "dedupe_key,run_id,employee_code,recipient,notification_type,"
                                "threshold_percent,status,attempt_count,created_at,updated_at"
                                ") VALUES(?,?,?,?,?,?, 'pending',0,?,?)",
                                (
                                    dedupe,
                                    run_id,
                                    snapshot.employee.code,
                                    recipient,
                                    mode,
                                    threshold,
                                    now.isoformat(),
                                    now.isoformat(),
                                ),
                            )
                            sendable.append((snapshot, threshold, dedupe))
                        except sqlite3.IntegrityError:
                            existing = conn.execute(
                                "SELECT status FROM notification_attempts "
                                "WHERE dedupe_key=? AND recipient=?",
                                (dedupe, recipient),
                            ).fetchone()
                            if existing and existing["status"] == "failed":
                                conn.execute(
                                    "UPDATE notification_attempts SET run_id=?, status='pending', "
                                    "error_message=NULL, updated_at=? "
                                    "WHERE dedupe_key=? AND recipient=?",
                                    (run_id, now.isoformat(), dedupe, recipient),
                                )
                                sendable.append((snapshot, threshold, dedupe))
                            else:
                                logger.info(
                                    "Duplicate notification skipped: %s -> %s", dedupe, recipient
                                )
            if not sendable:
                continue
            message = (
                "残業時間レポート\n"
                + "=" * 29
                + "\n\n"
                + "\n\n".join(_report(snapshot) for snapshot, _, _ in sendable)
            )
            if dry_run:
                logger.info("DRY RUN recipient=%s\n%s", recipient, message)
                continue
            try:
                slack_ts = messenger.send_dm(recipient, message)
                status, error = "sent", None
            except SlackDeliveryError as exc:
                failed += 1
                status, slack_ts, error = "failed", None, str(exc)
            with db.transaction() as conn:
                for _, _, dedupe in sendable:
                    conn.execute(
                        "UPDATE notification_attempts SET status=?, attempt_count=attempt_count+1,"
                        "slack_timestamp=?, error_message=?, updated_at=? "
                        "WHERE dedupe_key=? AND recipient=?",
                        (
                            status,
                            slack_ts,
                            error,
                            datetime.now(config.timezone).isoformat(),
                            dedupe,
                            recipient,
                        ),
                    )
        db.finish_run(
            run_id,
            datetime.now(config.timezone),
            "succeeded" if failed == 0 else "failed",
            None if failed == 0 else f"{failed} recipient(s) failed",
        )
        return 0 if failed == 0 else 4
    except Exception as exc:
        logger.exception("Run failed")
        db.finish_run(run_id, datetime.now(config.timezone), "failed", str(exc))
        return 1
