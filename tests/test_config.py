from __future__ import annotations

from pathlib import Path

from division_overtime.config import _deep_merge, load_config


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
                "ALL": ["h-tanaka@runsystem.co.jp"],
            },
        }
    }

    merged = _deep_merge(base, override)

    assert merged["notifications"]["enable_self_notify"] is False
    assert merged["notifications"]["department_recipients"] == {"ALL": ["h-tanaka@runsystem.co.jp"]}


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
ALL = ["h-tanaka@runsystem.co.jp"]
""".strip(),
        encoding="utf-8",
    )
    (data_dir / "employeeKey.csv").write_text("", encoding="utf-8")
    monkeypatch.setenv("KINGOFTIME_TOKEN", "kot-token")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "slack-token")

    config = load_config(tmp_path)

    assert config.enable_self_notify is False
    assert config.self_notify_employee_codes == frozenset()
    assert config.department_recipients == {"ALL": ("h-tanaka@runsystem.co.jp",)}
