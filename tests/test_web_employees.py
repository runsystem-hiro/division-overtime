from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from division_overtime.database import Database
from division_overtime.employee_repository import EmployeeRepository
from division_overtime.models import Employee
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


def _client(tmp_path: Path) -> TestClient:
    config = _config(tmp_path)
    db = Database(config.database_path)
    db.initialize()
    EmployeeRepository(db).upsert_many(
        [Employee("00001", "secret-key", "田中", "太郎", "a@example.com", "300", "営業部")],
        datetime(2026, 7, 23, 10, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
    )
    config.employee_csv.parent.mkdir(parents=True)
    config.employee_csv.write_text(
        "社員番号,キー,氏,名,メールアドレス,部署コード,部署名,個人別残業上限分\n"
        "00001,secret-key,田中,太郎,a@example.com,300,営業部,\n",
        encoding="utf-8",
    )
    client = TestClient(create_app(config))
    login = client.post(
        "/api/auth/login", json={"username": "hiro", "password": "correct-password"}
    )
    assert login.status_code == 200
    return client


def test_employee_api_requires_authentication(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))
    assert client.get("/api/employees").status_code == 401


def test_employee_list_never_returns_kot_key(tmp_path):
    client = _client(tmp_path)

    response = client.get("/api/employees")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["code"] == "00001"
    assert "employeeKey" not in body[0]
    assert "kotKey" not in body[0]
    assert "secret-key" not in response.text


def test_employee_create_and_update_regenerate_csv(tmp_path):
    client = _client(tmp_path)
    create_payload = {
        "code": "00002",
        "employeeKey": "key-2",
        "lastName": "佐藤",
        "firstName": "花子",
        "email": "b@example.com",
        "divisionCode": "301",
        "divisionName": "開発部",
        "personalTargetMinutes": 1200,
        "isEnabled": True,
        "disabledReason": "",
        "note": "",
    }

    created = client.post("/api/employees", json=create_payload)
    assert created.status_code == 201
    assert created.json()["employee"]["code"] == "00002"
    created_csv = created.json()["csv"]
    assert created_csv["regenerated"] is True
    assert created_csv["status"] == "success"
    assert created_csv["employeeCount"] == 2
    assert created_csv["outputPath"] == str(tmp_path / "data/employeeKey.csv")
    assert created_csv["generatedAt"]
    assert created_csv["backupPath"]
    assert Path(created_csv["backupPath"]).exists()
    assert "employeeKey" not in created.json()["employee"]
    assert "key-2" not in created.text

    update_payload = {**create_payload, "employeeKey": None, "divisionName": "開発本部"}
    updated = client.put("/api/employees/00002", json=update_payload)
    assert updated.status_code == 200
    assert updated.json()["employee"]["divisionName"] == "開発本部"
    updated_csv = updated.json()["csv"]
    assert updated_csv["regenerated"] is True
    assert updated_csv["status"] == "success"
    assert updated_csv["employeeCount"] == 2
    assert updated_csv["outputPath"] == str(tmp_path / "data/employeeKey.csv")
    assert updated_csv["generatedAt"]
    assert updated_csv["backupPath"]
    assert Path(updated_csv["backupPath"]).exists()
    assert "key-2" not in updated.text

    csv_text = (tmp_path / "data/employeeKey.csv").read_text(encoding="utf-8-sig")
    assert "00002,key-2,佐藤,花子" in csv_text
    assert "開発本部" in csv_text


def test_employee_consistency_api_requires_authentication(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    response = client.get("/api/employees/consistency")

    assert response.status_code == 401


def test_employee_consistency_api_reports_match_without_secrets(tmp_path):
    client = _client(tmp_path)

    response = client.get("/api/employees/consistency")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "databaseEmployees": 1,
        "csvEmployees": 1,
        "databaseOnlyCodes": [],
        "csvOnlyCodes": [],
        "fieldDifferences": [],
    }
    assert "secret-key" not in response.text


def test_employee_consistency_api_reports_codes_and_field_names_only(tmp_path):
    client = _client(tmp_path)
    csv_path = tmp_path / "data/employeeKey.csv"
    csv_path.write_text(
        "社員番号,キー,氏,名,メールアドレス,部署コード,部署名,個人別残業上限分\n"
        "00001,different-secret,田中,太郎,changed@example.com,300,営業部,\n"
        "00002,csv-only,佐藤,花子,b@example.com,301,開発部,\n",
        encoding="utf-8",
    )

    response = client.get("/api/employees/consistency")

    assert response.status_code == 200
    assert response.json() == {
        "status": "mismatch",
        "databaseEmployees": 1,
        "csvEmployees": 2,
        "databaseOnlyCodes": [],
        "csvOnlyCodes": ["00002"],
        "fieldDifferences": [{"code": "00001", "fields": ["kot_key", "email"]}],
    }
    assert "secret-key" not in response.text
    assert "different-secret" not in response.text
    assert "csv-only" not in response.text
