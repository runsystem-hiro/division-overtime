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


def _set_auth_env(monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_USERNAME", "hiro")
    monkeypatch.setenv("WEB_ADMIN_PASSWORD_HASH", "$argon2id$example")
    monkeypatch.setenv("WEB_SESSION_SECRET", "s" * 48)


def test_load_web_config_does_not_require_external_tokens(tmp_path, monkeypatch):
    _write_default(tmp_path)
    _set_auth_env(monkeypatch)
    monkeypatch.delenv("KINGOFTIME_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.setenv("WEB_PORT", "8123")

    config = load_web_config(tmp_path)

    assert config.root == tmp_path.resolve()
    assert config.port == 8123
    assert config.admin_username == "hiro"
    assert config.session_cookie_name == "division_overtime_session"
    assert config.session_cookie_secure is False
    assert config.session_max_age_seconds == 28800


def test_load_web_config_rejects_invalid_port(tmp_path, monkeypatch):
    _write_default(tmp_path)
    _set_auth_env(monkeypatch)
    monkeypatch.setenv("WEB_PORT", "70000")

    with pytest.raises(WebConfigError, match="between 1 and 65535"):
        load_web_config(tmp_path)


def test_load_web_config_requires_authentication_secrets(tmp_path, monkeypatch):
    _write_default(tmp_path)
    monkeypatch.delenv("WEB_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("WEB_ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("WEB_SESSION_SECRET", raising=False)

    with pytest.raises(WebConfigError, match="WEB_SESSION_SECRET"):
        load_web_config(tmp_path)


def test_load_web_config_rejects_short_session_secret(tmp_path, monkeypatch):
    _write_default(tmp_path)
    _set_auth_env(monkeypatch)
    monkeypatch.setenv("WEB_SESSION_SECRET", "too-short")

    with pytest.raises(WebConfigError, match="at least 32"):
        load_web_config(tmp_path)


def test_load_web_config_uses_development_paths(tmp_path, monkeypatch):
    _write_default(tmp_path)
    (tmp_path / "config/development.toml").write_text(
        """
[app]
database_path = "var/development/overtime.db"
employee_csv = "data/development/employeeKey.csv"

[king_of_time]
enabled = false
mock_enabled = true
""".strip(),
        encoding="utf-8",
    )
    _set_auth_env(monkeypatch)
    monkeypatch.setenv("DIVISION_OVERTIME_ENV", "development")

    config = load_web_config(tmp_path)

    assert config.database_path == tmp_path / "var/development/overtime.db"
    assert config.employee_csv == tmp_path / "data/development/employeeKey.csv"
    assert config.environment == "development"
    assert config.kot_enabled is False
    assert config.kot_mock_enabled is True
