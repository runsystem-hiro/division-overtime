from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from division_overtime.database import Database
from division_overtime.development_data import development_employees
from division_overtime.employee_management import EmployeeManagementService
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
        [
            Employee("00001", "old", "田中", "太郎", "", "300", "営業部"),
            Employee("00003", "key-3", "鈴木", "次郎", "", "300", "営業部"),
        ],
        datetime.now(ZoneInfo("Asia/Tokyo")),
    )
    with db.transaction() as conn:
        conn.execute("UPDATE employees SET is_enabled=0 WHERE code='00003'")
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
    body = response.json()
    assert "hidden-key" not in response.text
    assert "key" not in body["differences"][0]["proposed"]
    assert body["counts"]["disable"] == 0
    assert "00003" not in {item["code"] for item in body["differences"]}


def test_preview_omits_already_disabled_resigned_employee_from_api(tmp_path: Path, monkeypatch):
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
    with db.transaction() as conn:
        conn.execute("UPDATE employees SET is_enabled=0 WHERE code='00001'")

    class ResignedClient:
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
                        "resignationDate": "2026-07-23",
                    }
                ]
            )

    app.state.kot_employee_sync_service = KotEmployeeSyncService(
        db, config.employee_csv, ResignedClient(), ("300",)
    )
    client = TestClient(app)
    client.post("/api/auth/login", json={"username": "hiro", "password": "pass"})

    response = client.post("/api/kot-sync/preview")

    assert response.status_code == 200
    assert response.json()["counts"]["disable"] == 0
    assert response.json()["differences"] == []
    assert "hidden-key" not in response.text


def test_kot_sync_is_rejected_when_disabled(tmp_path: Path):
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
        kot_token="configured-but-unused",
        kot_connect_timeout=5,
        kot_read_timeout=30,
        kot_retry_count=1,
        kot_retry_backoff=0,
        environment="development",
        kot_enabled=False,
    )
    client = TestClient(create_app(config))
    client.post("/api/auth/login", json={"username": "hiro", "password": "pass"})
    assert client.get("/api/kot-sync/status").status_code == 403
    assert client.post("/api/kot-sync/preview").status_code == 403


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
    assert body["counts"] == {"created": 0, "updated": 1, "reactivated": 0, "disabled": 0}
    backup_path = Path(body["backupPath"])
    assert backup_path.parent == backup_root
    assert (backup_path / "db.sqlite3").exists()
    assert (backup_path / "employeeKey.csv").read_text(encoding="utf-8") == "original-csv"
    status = client.get("/api/kot-sync/status")
    assert status.status_code == 200
    assert status.json()["lastRun"]["backup_path"] == str(backup_path)
    assert "hidden-key" not in response.text
    assert "hidden-key" not in status.text


def test_api_supports_reactivate_preview_apply_and_status(tmp_path: Path, monkeypatch):
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
        [Employee("00001", "old", "田中", "太郎", "local@example.com", "300", "営業部", 1500)],
        datetime.now(ZoneInfo("Asia/Tokyo")),
    )
    with db.transaction() as conn:
        conn.execute(
            "UPDATE employees SET is_enabled=0, disabled_reason='手動無効化' WHERE code='00001'"
        )
    app.state.kot_employee_sync_service = KotEmployeeSyncService(
        db, config.employee_csv, FakeClient(), ("300",)
    )
    client = TestClient(app)
    client.post("/api/auth/login", json={"username": "hiro", "password": "pass"})

    preview = client.post("/api/kot-sync/preview")
    assert preview.status_code == 200
    body = preview.json()
    assert body["counts"]["reactivate"] == 1
    assert body["differences"][0]["action"] == "reactivate"

    applied = client.post(
        "/api/kot-sync/apply",
        json={"previewId": body["previewId"], "employeeCodes": ["00001"]},
    )
    assert applied.status_code == 200
    assert applied.json()["counts"]["reactivated"] == 1
    status = client.get("/api/kot-sync/status").json()
    assert status["lastRun"]["reactivated_count"] == 1


def test_development_mock_preview_contains_all_actions(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "division_overtime.sqlite3"
    employee_csv = tmp_path / "employeeKey.csv"
    config = WebConfig(
        root=root,
        timezone=ZoneInfo("Asia/Tokyo"),
        database_path=database_path,
        employee_csv=employee_csv,
        frontend_dist=root / "frontend/dist",
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
        kot_token="configured-but-unused",
        kot_connect_timeout=5,
        kot_read_timeout=30,
        kot_retry_count=1,
        kot_retry_backoff=0,
        kot_sync_division_codes=("156", "158"),
        environment="development",
        kot_enabled=False,
        kot_mock_enabled=True,
    )
    db = Database(database_path)
    db.initialize()
    service = EmployeeManagementService(db, employee_csv)
    now = datetime.now(ZoneInfo("Asia/Tokyo"))
    for employee in development_employees():
        service.create_employee(employee, now)

    app = create_app(config)
    client = TestClient(app)
    client.post("/api/auth/login", json={"username": "hiro", "password": "pass"})

    health = client.get("/api/system/health")
    assert health.status_code == 200
    assert health.json()["kotSyncEnabled"] is True
    assert health.json()["kotSyncMock"] is True

    status = client.get("/api/kot-sync/status")
    assert status.status_code == 200
    assert status.json()["blocked"] is False

    preview = client.post("/api/kot-sync/preview")
    assert preview.status_code == 200
    body = preview.json()
    assert body["counts"] == {
        "create": 1,
        "update": 1,
        "reactivate": 1,
        "disable": 1,
        "unchanged": 1,
    }
    assert {item["action"] for item in body["differences"]} == {
        "create",
        "update",
        "reactivate",
        "disable",
        "unchanged",
    }
    assert "configured-but-unused" not in preview.text

    selected_codes = [item["code"] for item in body["differences"] if item["action"] != "unchanged"]
    applied = client.post(
        "/api/kot-sync/apply",
        json={"previewId": body["previewId"], "employeeCodes": selected_codes},
    )
    assert applied.status_code == 200
    assert applied.json()["counts"] == {
        "created": 1,
        "updated": 1,
        "reactivated": 1,
        "disabled": 1,
    }
    assert employee_csv.exists()
    employees = {employee.code: employee for employee in EmployeeRepository(db).list_managed()}
    assert employees["90003"].is_enabled is False
    assert employees["90004"].is_enabled is True
    assert employees["90005"].is_enabled is True
