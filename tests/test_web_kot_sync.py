from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from division_overtime.database import Database
from division_overtime.employee_repository import EmployeeRepository
from division_overtime.kot_employee_sync import KotEmployeeSyncService, parse_kot_employees
from division_overtime.models import Employee
from division_overtime.web.app import create_app
from division_overtime.web.config import WebConfig


class FakeClient:
    def fetch(self):
        return parse_kot_employees(
            [
                {
                    "code": "00001",
                    "key": "hidden-key",
                    "lastName": "田中",
                    "firstName": "太郎",
                    "divisionCode": "300",
                    "divisionName": "営業部",
                    "employeeGroups": [],
                }
            ]
        )


def test_preview_requires_auth_and_never_exposes_kot_key(tmp_path: Path, monkeypatch):
    config = WebConfig(
        root=tmp_path,
        timezone=ZoneInfo("Asia/Tokyo"),
        database_path=tmp_path / "db.sqlite3",
        employee_csv=tmp_path / "employeeKey.csv",
        frontend_dist=tmp_path / "dist",
        host="0.0.0.0",
        port=8000,
        log_level="INFO",
        admin_username="hiro",
        admin_password_hash=PasswordHasher().hash("pass"),
        session_secret="s" * 48,
        session_cookie_name="session",
        session_cookie_secure=False,
        session_max_age_seconds=28800,
        login_max_attempts=5,
        login_window_seconds=900,
        login_lockout_seconds=900,
        kot_base_url="https://api.kingtime.jp/v1.0",
        kot_token="",
        kot_connect_timeout=5,
        kot_read_timeout=30,
        kot_retry_count=1,
        kot_retry_backoff=0,
        kot_sync_division_codes=("156", "158", "300"),
    )
    monkeypatch.setattr("division_overtime.web.routes.kot_sync._is_api_blocked", lambda _now: False)
    app = create_app(config)
    db = Database(config.database_path)
    EmployeeRepository(db).upsert_many(
        [Employee("00001", "old", "田中", "太郎", "", "300", "営業部")],
        datetime.now(ZoneInfo("Asia/Tokyo")),
    )
    app.state.kot_employee_sync_service = KotEmployeeSyncService(
        db, config.employee_csv, FakeClient(), ("300", "301")
    )
    client = TestClient(app)
    assert client.post("/api/kot-sync/preview").status_code == 401
    assert (
        client.post("/api/auth/login", json={"username": "hiro", "password": "pass"}).status_code
        == 200
    )

    response = client.post("/api/kot-sync/preview")

    assert response.status_code == 200
    assert "hidden-key" not in response.text
    assert "key" not in response.json()["differences"][0]["proposed"]


def test_kot_sync_blocked_time_detection():
    from division_overtime.web.routes.kot_sync import _is_api_blocked

    timezone = ZoneInfo("Asia/Tokyo")
    assert _is_api_blocked(datetime(2026, 7, 23, 8, 30, tzinfo=timezone))
    assert _is_api_blocked(datetime(2026, 7, 23, 17, 30, tzinfo=timezone))
    assert not _is_api_blocked(datetime(2026, 7, 23, 10, 0, tzinfo=timezone))
    assert not _is_api_blocked(datetime(2026, 7, 23, 18, 30, tzinfo=timezone))


def test_kot_sync_status_requires_auth_and_hides_secrets(tmp_path: Path):
    config = WebConfig(
        root=tmp_path,
        timezone=ZoneInfo("Asia/Tokyo"),
        database_path=tmp_path / "db.sqlite3",
        employee_csv=tmp_path / "employeeKey.csv",
        frontend_dist=tmp_path / "dist",
        host="0.0.0.0",
        port=8000,
        log_level="INFO",
        admin_username="hiro",
        admin_password_hash=PasswordHasher().hash("pass"),
        session_secret="s" * 48,
        session_cookie_name="session",
        session_cookie_secure=False,
        session_max_age_seconds=28800,
        login_max_attempts=5,
        login_window_seconds=900,
        login_lockout_seconds=900,
        kot_base_url="https://api.kingtime.jp/v1.0",
        kot_token="",
        kot_connect_timeout=5,
        kot_read_timeout=30,
        kot_retry_count=1,
        kot_retry_backoff=0,
        kot_sync_division_codes=("300",),
    )
    app = create_app(config)
    db = Database(config.database_path)
    app.state.kot_employee_sync_service = KotEmployeeSyncService(
        db, config.employee_csv, FakeClient(), ("300",)
    )
    client = TestClient(app)

    assert client.get("/api/kot-sync/status").status_code == 401
    client.post("/api/auth/login", json={"username": "hiro", "password": "pass"})
    response = client.get("/api/kot-sync/status")

    assert response.status_code == 200
    assert set(response.json()) == {"running", "blocked", "lastRun"}
    assert "hidden-key" not in response.text


def test_apply_returns_backup_path_and_hides_secrets(tmp_path: Path, monkeypatch):
    config = WebConfig(
        root=tmp_path,
        timezone=ZoneInfo("Asia/Tokyo"),
        database_path=tmp_path / "db.sqlite3",
        employee_csv=tmp_path / "employeeKey.csv",
        frontend_dist=tmp_path / "dist",
        host="0.0.0.0",
        port=8000,
        log_level="INFO",
        admin_username="hiro",
        admin_password_hash=PasswordHasher().hash("pass"),
        session_secret="s" * 48,
        session_cookie_name="session",
        session_cookie_secure=False,
        session_max_age_seconds=28800,
        login_max_attempts=5,
        login_window_seconds=900,
        login_lockout_seconds=900,
        kot_base_url="https://api.kingtime.jp/v1.0",
        kot_token="",
        kot_connect_timeout=5,
        kot_read_timeout=30,
        kot_retry_count=1,
        kot_retry_backoff=0,
        kot_sync_division_codes=("300",),
    )
    monkeypatch.setattr("division_overtime.web.routes.kot_sync._is_api_blocked", lambda _now: False)
    app = create_app(config)
    db = Database(config.database_path)
    EmployeeRepository(db).upsert_many(
        [Employee("00001", "old", "田中", "太郎", "", "300", "営業部")],
        datetime.now(ZoneInfo("Asia/Tokyo")),
    )
    config.employee_csv.write_text("original-csv", encoding="utf-8")
    backup_root = tmp_path / "backups"
    app.state.kot_employee_sync_service = KotEmployeeSyncService(
        db, config.employee_csv, FakeClient(), ("300",), backup_root=backup_root
    )
    client = TestClient(app)
    client.post("/api/auth/login", json={"username": "hiro", "password": "pass"})
    preview = client.post("/api/kot-sync/preview").json()

    response = client.post(
        "/api/kot-sync/apply",
        json={"previewId": preview["previewId"], "employeeCodes": ["00001"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["counts"] == {"created": 0, "updated": 1, "disabled": 0}
    backup_path = Path(body["backupPath"])
    assert backup_path.parent == backup_root
    assert (backup_path / "db.sqlite3").exists()
    assert (backup_path / "employeeKey.csv").read_text(encoding="utf-8") == "original-csv"
    assert "hidden-key" not in response.text
