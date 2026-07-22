from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from division_overtime.web.app import create_app
from division_overtime.web.config import WebConfig


def _config(root: Path, *, max_attempts: int = 5, max_age: int = 28800) -> WebConfig:
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
        session_max_age_seconds=max_age,
        login_max_attempts=max_attempts,
        login_window_seconds=900,
        login_lockout_seconds=900,
    )


def _login(client: TestClient, password: str = "correct-password"):
    return client.post("/api/auth/login", json={"username": "hiro", "password": password})


def test_health_and_version_endpoints_are_public(tmp_path):
    (tmp_path / "VERSION").write_text("1.0.2\n", encoding="utf-8")
    client = TestClient(create_app(_config(tmp_path)))

    health = client.get("/api/system/health")
    version = client.get("/api/version")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["version"] == "1.0.2"
    assert version.json() == {"version": "1.0.2"}


def test_root_reports_frontend_not_built(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))
    response = client.get("/")
    assert response.status_code == 503
    assert response.json()["status"] == "frontend_not_built"


def test_built_frontend_is_served(tmp_path):
    dist = tmp_path / "frontend/dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<h1>ready</h1>", encoding="utf-8")
    client = TestClient(create_app(_config(tmp_path)))

    assert "ready" in client.get("/").text
    assert "ready" in client.get("/employees").text


def test_login_me_logout_flow_and_cookie_attributes(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    assert client.get("/api/auth/me").status_code == 401
    login = _login(client)
    assert login.status_code == 200
    assert login.json()["username"] == "hiro"
    cookie = login.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "secure" not in cookie

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "hiro"

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_invalid_credentials_do_not_reveal_which_field_failed(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))
    wrong_user = client.post(
        "/api/auth/login", json={"username": "unknown", "password": "correct-password"}
    )
    wrong_password = _login(client, "wrong-password")

    assert wrong_user.status_code == 401
    assert wrong_password.status_code == 401
    assert wrong_user.json() == wrong_password.json()


def test_login_rate_limit(tmp_path):
    client = TestClient(create_app(_config(tmp_path, max_attempts=2)))

    assert _login(client, "wrong-1").status_code == 401
    assert _login(client, "wrong-2").status_code == 401
    assert _login(client).status_code == 429
