from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from division_overtime.config import AppConfig
from division_overtime.database import Database
from division_overtime.service import run
from division_overtime.slack import SlackDeliveryError


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 7, 22, 10, 30, 0)
        return value.replace(tzinfo=tz) if tz else value


class FakeKingOfTimeClient:
    current_minutes = 360
    previous_minutes = 300

    def __init__(self, *args, **kwargs):
        pass

    def fetch_division_month(self, target_month: str, division_code: str) -> dict[str, int]:
        minutes = self.previous_minutes if target_month == "2026-06" else self.current_minutes
        return {"employee-key-1": minutes}


class SuccessfulMessenger:
    calls: list[tuple[str, str]] = []

    def __init__(self, token: str):
        pass

    def send_dm(self, recipient: str, message: str) -> str:
        self.calls.append((recipient, message))
        return "1712345678.000100"


class FailingMessenger:
    calls: list[tuple[str, str]] = []

    def __init__(self, token: str):
        pass

    def send_dm(self, recipient: str, message: str) -> str:
        self.calls.append((recipient, message))
        raise SlackDeliveryError("temporary Slack failure")


def make_config(tmp_path: Path) -> AppConfig:
    employee_csv = tmp_path / "employeeKey.csv"
    employee_csv.write_text(
        "社員番号,キー,氏,名,メールアドレス,"
        "部署コード,部署名,個人別残業上限分\n"
        "00001,employee-key-1,田中,太郎,tanaka@example.com,300,営業部,600\n",
        encoding="utf-8",
    )
    return AppConfig(
        root=tmp_path,
        timezone=ZoneInfo("Asia/Tokyo"),
        database_path=tmp_path / "var" / "division_overtime.sqlite3",
        employee_csv=employee_csv,
        log_level="INFO",
        kot_base_url="https://example.invalid",
        kot_endpoint="/api/overtime",
        kot_token="kot-token",
        connect_timeout=3.0,
        read_timeout=10.0,
        retry_count=2,
        retry_backoff=0.1,
        default_target_minutes=600,
        thresholds=(60, 70, 80, 90, 100),
        division_targets={"300": 600},
        slack_token="slack-token",
        department_recipients={"300": ("manager@example.com",)},
        enable_self_notify=False,
        self_notify_employee_codes=frozenset(),
        force_self_threshold=95,
    )


def patch_external_services(monkeypatch: pytest.MonkeyPatch, messenger_type: type) -> None:
    monkeypatch.setattr("division_overtime.service.datetime", FixedDateTime)
    monkeypatch.setattr("division_overtime.service.jpholiday.is_holiday", lambda _date: False)
    monkeypatch.setattr("division_overtime.service.KingOfTimeClient", FakeKingOfTimeClient)
    monkeypatch.setattr("division_overtime.service.SlackMessenger", messenger_type)
    messenger_type.calls.clear()


def fetch_attempts(database_path: Path) -> list[sqlite3.Row]:
    db = Database(database_path)
    with db.connect() as conn:
        return list(
            conn.execute(
                "SELECT recipient,status,attempt_count,slack_timestamp,error_message "
                "FROM notification_attempts ORDER BY id"
            )
        )


def test_threshold_success_is_recorded_and_duplicate_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = make_config(tmp_path)
    patch_external_services(monkeypatch, SuccessfulMessenger)

    assert run(config, "threshold") == 0
    assert run(config, "threshold") == 0

    attempts = fetch_attempts(config.database_path)
    assert len(attempts) == 1
    assert attempts[0]["recipient"] == "manager@example.com"
    assert attempts[0]["status"] == "sent"
    assert attempts[0]["attempt_count"] == 1
    assert attempts[0]["slack_timestamp"] == "1712345678.000100"
    assert len(SuccessfulMessenger.calls) == 1


def test_failed_notification_is_retried_and_marked_sent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = make_config(tmp_path)
    patch_external_services(monkeypatch, FailingMessenger)

    assert run(config, "threshold") == 4
    failed_attempt = fetch_attempts(config.database_path)[0]
    assert failed_attempt["status"] == "failed"
    assert failed_attempt["attempt_count"] == 1
    assert "temporary Slack failure" in failed_attempt["error_message"]

    patch_external_services(monkeypatch, SuccessfulMessenger)
    assert run(config, "threshold") == 0

    attempts = fetch_attempts(config.database_path)
    assert len(attempts) == 1
    assert attempts[0]["status"] == "sent"
    assert attempts[0]["attempt_count"] == 2
    assert attempts[0]["error_message"] is None
    assert len(SuccessfulMessenger.calls) == 1


def test_dry_run_does_not_consume_notification_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = make_config(tmp_path)
    patch_external_services(monkeypatch, SuccessfulMessenger)

    assert run(config, "threshold", dry_run=True) == 0
    assert fetch_attempts(config.database_path) == []
    assert SuccessfulMessenger.calls == []

    assert run(config, "threshold") == 0
    attempts = fetch_attempts(config.database_path)
    assert len(attempts) == 1
    assert attempts[0]["status"] == "sent"
    assert len(SuccessfulMessenger.calls) == 1
