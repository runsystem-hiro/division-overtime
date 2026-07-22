from __future__ import annotations

from pathlib import Path

import pytest

from division_overtime.web.config import WebConfigError, load_web_config


def _write_default(root: Path) -> None:
    config_dir = root / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "default.toml").write_text(
        """
[app]
timezone = "Asia/Tokyo"
database_path = "var/overtime.db"
employee_csv = "data/employeeKey.csv"
log_level = "INFO"
""".strip(),
        encoding="utf-8",
    )


def test_load_web_config_does_not_require_external_tokens(tmp_path, monkeypatch):
    _write_default(tmp_path)
    monkeypatch.delenv("KINGOFTIME_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.setenv("WEB_PORT", "8123")

    config = load_web_config(tmp_path)

    assert config.root == tmp_path.resolve()
    assert config.port == 8123
    assert config.database_path == tmp_path / "var/overtime.db"
    assert config.employee_csv == tmp_path / "data/employeeKey.csv"
    assert config.frontend_dist == tmp_path / "frontend/dist"


def test_load_web_config_rejects_invalid_port(tmp_path, monkeypatch):
    _write_default(tmp_path)
    monkeypatch.setenv("WEB_PORT", "70000")

    with pytest.raises(WebConfigError, match="between 1 and 65535"):
        load_web_config(tmp_path)
