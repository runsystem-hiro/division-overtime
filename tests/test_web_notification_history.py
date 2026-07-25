from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from division_overtime.database import Database
from division_overtime.web.app import create_app
from division_overtime.web.config import WebConfig


def _config(root: Path) -> WebConfig:
    return WebConfig(
        root=root,
        timezone=ZoneInfo("Asia/Tokyo"),
        database_path=root / "var/overtime.db",
        employee_csv=root / "data/employeeKey.csv",
        frontend_dist=root / "frontend/dist",
        host="0.0.0.0",
        port=8000,
        log_level="INFO",
        admin_username="hiro",
        admin_password_hash=PasswordHasher().hash("correct-password"),
        session_secret="s" * 48,
        session_cookie_name="division_overtime_session",
        session_cookie_secure=False,
        session_max_age_seconds=28800,
        login_max_attempts=5,
        login_window_seconds=900,
        login_lockout_seconds=900,
        kot_base_url="https://api.kingtime.jp/v1.0",
        kot_token="",
        kot_connect_timeout=5.0,
        kot_read_timeout=30.0,
        kot_retry_count=1,
        kot_retry_backoff=0.0,
    )


def _client(tmp_path: Path) -> tuple[TestClient, Database]:
    config = _config(tmp_path)
    database = Database(config.database_path)
    database.initialize()
    client = TestClient(create_app(config))
    login = client.post(
        "/api/auth/login", json={"username": "hiro", "password": "correct-password"}
    )
    assert login.status_code == 200
    return client, database


def _seed_history(database: Database) -> None:
    with database.transaction() as conn:
        conn.execute(
            """
            INSERT INTO execution_runs(
                run_id, mode, started_at, finished_at, status, dry_run, error_message
            ) VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "weekly-20260725",
                "weekly",
                "2026-07-25T06:30:00+09:00",
                "2026-07-25T06:30:03+09:00",
                "succeeded",
                0,
                None,
            ),
        )
        conn.executemany(
            """
            INSERT INTO overtime_snapshots(
                run_id, target_month, employee_code, employee_name, division_code,
                current_minutes, previous_minutes, target_minutes, target_percent,
                captured_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "weekly-20260725",
                    "2026-07",
                    "00001",
                    "田中 太郎",
                    "300",
                    1200,
                    900,
                    2700,
                    80,
                    "2026-07-25T06:30:01+09:00",
                ),
                (
                    "weekly-20260725",
                    "2026-07",
                    "00002",
                    "佐藤 花子",
                    "300",
                    1000,
                    800,
                    2700,
                    80,
                    "2026-07-25T06:30:01+09:00",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO notification_attempts(
                dedupe_key, run_id, employee_code, recipient, notification_type,
                threshold_percent, status, attempt_count, slack_timestamp,
                error_message, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "weekly:2026-W30:U001",
                    "weekly-20260725",
                    None,
                    "U001",
                    "weekly",
                    None,
                    "sent",
                    1,
                    "1753392600.000001",
                    None,
                    "2026-07-25T06:30:02+09:00",
                    "2026-07-25T06:30:02+09:00",
                ),
                (
                    "weekly:2026-W30:U002",
                    "weekly-20260725",
                    None,
                    "U002",
                    "weekly",
                    None,
                    "failed",
                    2,
                    None,
                    "Slack API error",
                    "2026-07-25T06:30:02+09:00",
                    "2026-07-25T06:30:03+09:00",
                ),
            ],
        )


def test_notification_history_api_requires_authentication(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    assert client.get("/api/notification-runs").status_code == 401
    assert client.get("/api/notification-runs/missing").status_code == 401


def test_notification_run_list_returns_existing_database_values(tmp_path):
    client, database = _client(tmp_path)
    _seed_history(database)

    response = client.get("/api/notification-runs?limit=10&offset=0")

    assert response.status_code == 200
    assert response.json() == [
        {
            "runId": "weekly-20260725",
            "mode": "weekly",
            "startedAt": "2026-07-25T06:30:00+09:00",
            "finishedAt": "2026-07-25T06:30:03+09:00",
            "status": "succeeded",
            "dryRun": False,
            "errorMessage": None,
            "targetCount": 2,
            "attemptCount": 2,
            "sentCount": 1,
            "failedCount": 1,
            "skippedCount": 0,
            "pendingCount": 0,
        }
    ]


def test_notification_run_detail_returns_attempts_without_secrets(tmp_path):
    client, database = _client(tmp_path)
    _seed_history(database)

    response = client.get("/api/notification-runs/weekly-20260725")

    assert response.status_code == 200
    body = response.json()
    assert body["runId"] == "weekly-20260725"
    assert body["attemptCount"] == 2
    assert [attempt["status"] for attempt in body["attempts"]] == ["sent", "failed"]
    assert body["attempts"][0]["recipient"] == "U001"
    assert body["attempts"][1]["errorMessage"] == "Slack API error"
    assert "token" not in response.text.lower()
    assert "password" not in response.text.lower()


def test_notification_run_detail_returns_404_for_unknown_run(tmp_path):
    client, _ = _client(tmp_path)

    response = client.get("/api/notification-runs/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Notification run not found."}


def test_notification_history_api_does_not_modify_database(tmp_path):
    client, database = _client(tmp_path)
    _seed_history(database)
    with database.connect_readonly() as conn:
        before = (
            conn.execute("SELECT COUNT(*) FROM execution_runs").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM notification_attempts").fetchone()[0],
        )

    assert client.get("/api/notification-runs").status_code == 200
    assert client.get("/api/notification-runs/weekly-20260725").status_code == 200

    with database.connect_readonly() as conn:
        after = (
            conn.execute("SELECT COUNT(*) FROM execution_runs").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM notification_attempts").fetchone()[0],
        )
    assert after == before
