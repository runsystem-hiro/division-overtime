from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

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
    )


def test_health_and_version_endpoints(tmp_path):
    (tmp_path / "VERSION").write_text("1.0.2\n", encoding="utf-8")
    client = TestClient(create_app(_config(tmp_path)))

    health = client.get("/api/system/health")
    version = client.get("/api/version")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["service"] == "division-overtime-web"
    assert health.json()["version"] == "1.0.2"
    assert health.json()["timezone"] == "Asia/Tokyo"
    assert health.json()["frontendBuilt"] is False
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

    response = client.get("/")
    fallback = client.get("/employees")

    assert response.status_code == 200
    assert "ready" in response.text
    assert fallback.status_code == 200
    assert "ready" in fallback.text
