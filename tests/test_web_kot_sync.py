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


def test_preview_requires_auth_and_never_exposes_kot_key(tmp_path: Path):
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
    )
    app = create_app(config)
    db = Database(config.database_path)
    EmployeeRepository(db).upsert_many(
        [Employee("00001", "old", "田中", "太郎", "", "300", "営業部")],
        datetime.now(ZoneInfo("Asia/Tokyo")),
    )
    app.state.kot_employee_sync_service = KotEmployeeSyncService(
        db, config.employee_csv, FakeClient()
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
