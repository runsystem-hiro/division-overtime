from __future__ import annotations

from pathlib import Path

import pytest

from division_overtime.config import ConfigError, _deep_merge, load_config


def test_department_recipients_are_replaced_not_merged() -> None:
    base = {
        "notifications": {
            "enable_self_notify": True,
            "department_recipients": {
                "ALL": ["admin@example.com"],
                "300": ["manager@example.com"],
                "158": ["leader@example.com"],
            },
        }
    }
    override = {
        "notifications": {
            "enable_self_notify": False,
            "department_recipients": {
                "ALL": ["developer@example.com"],
            },
        }
    }

    merged = _deep_merge(base, override)

    assert merged["notifications"]["enable_self_notify"] is False
    assert merged["notifications"]["department_recipients"] == {"ALL": ["developer@example.com"]}


def test_load_config_uses_only_production_recipients(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    data_dir.mkdir()

    (config_dir / "default.toml").write_text(
        """
[app]
timezone = "Asia/Tokyo"
database_path = "var/division_overtime.sqlite3"
employee_csv = "data/employeeKey.csv"
log_level = "INFO"

[king_of_time]
base_url = "https://example.invalid"
endpoint = "/monthly-workings"
connect_timeout_seconds = 5
read_timeout_seconds = 30
retry_count = 3
retry_backoff_seconds = 2

[overtime]
default_target_minutes = 600
thresholds = [60, 70, 80, 90, 100]
force_self_threshold = 95

[overtime.division_targets]
"300" = 600

[notifications]
enable_self_notify = true
self_notify_employee_codes = ["00001"]

[notifications.department_recipients]
ALL = ["admin@example.com"]
"300" = ["manager@example.com"]
"158" = ["leader@example.com"]
""".strip(),
        encoding="utf-8",
    )
    (config_dir / "production.toml").write_text(
        """
[notifications]
enable_self_notify = false
self_notify_employee_codes = []

[notifications.department_recipients]
ALL = ["developer@example.com"]
""".strip(),
        encoding="utf-8",
    )
    (data_dir / "employeeKey.csv").write_text("", encoding="utf-8")
    monkeypatch.setenv("KINGOFTIME_TOKEN", "kot-token")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "slack-token")

    config = load_config(tmp_path)

    assert config.enable_self_notify is False
    assert config.self_notify_employee_codes == frozenset()
    assert config.department_recipients == {"ALL": ("developer@example.com",)}


def test_load_config_uses_development_override(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.toml").write_text(
        (Path(__file__).parents[1] / "config/default.toml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (config_dir / "development.toml").write_text(
        """
[app]
database_path = "var/development/test.sqlite3"
employee_csv = "data/development/employeeKey.csv"

[king_of_time]
enabled = false
mock_enabled = true

[notifications]
enable_self_notify = false
self_notify_employee_codes = []

[notifications.department_recipients]
ALL = ["developer@example.com"]
"156" = []
"158" = []
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("DIVISION_OVERTIME_ENV", "development")
    monkeypatch.delenv("KINGOFTIME_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)

    config = load_config(tmp_path)

    assert config.environment == "development"
    assert config.kot_enabled is False
    assert config.kot_mock_enabled is True
    assert config.kot_token == ""
    assert config.slack_token == ""
    assert config.database_path == tmp_path / "var/development/test.sqlite3"
    assert config.employee_csv == tmp_path / "data/development/employeeKey.csv"
    assert config.department_recipients == {
        "ALL": ("developer@example.com",),
        "156": (),
        "158": (),
    }


def test_development_rejects_real_kot_configuration(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.toml").write_text(
        (Path(__file__).parents[1] / "config/default.toml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (config_dir / "development.toml").write_text(
        "[king_of_time]\nenabled = true\nmock_enabled = false\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DIVISION_OVERTIME_ENV", "development")

    with pytest.raises(
        ConfigError,
        match="development requires king_of_time.enabled=false and mock_enabled=true",
    ):
        load_config(tmp_path)


def test_production_rejects_kot_mock(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.toml").write_text(
        (Path(__file__).parents[1] / "config/default.toml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (config_dir / "production.toml").write_text(
        "[king_of_time]\nmock_enabled = true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DIVISION_OVERTIME_ENV", "production")
    monkeypatch.setenv("KINGOFTIME_TOKEN", "kot-token")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "slack-token")

    with pytest.raises(ConfigError, match="allowed only in development"):
        load_config(tmp_path)
