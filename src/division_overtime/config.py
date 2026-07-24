from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AppConfig:
    root: Path
    timezone: ZoneInfo
    database_path: Path
    employee_csv: Path
    log_level: str
    kot_base_url: str
    kot_endpoint: str
    kot_token: str
    connect_timeout: float
    read_timeout: float
    retry_count: int
    retry_backoff: float
    default_target_minutes: int
    thresholds: tuple[int, ...]
    division_targets: dict[str, int]
    slack_token: str
    department_recipients: dict[str, tuple[str, ...]]
    enable_self_notify: bool
    self_notify_employee_codes: frozenset[str]
    force_self_threshold: int


_REPLACE_TABLE_PATHS = {("notifications", "department_recipients")}
_SUPPORTED_ENVIRONMENTS = {"development", "production"}


def _deep_merge(
    base: dict[str, Any],
    override: dict[str, Any],
    path: tuple[str, ...] = (),
) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        current_path = (*path, key)
        if current_path in _REPLACE_TABLE_PATHS:
            result[key] = dict(value) if isinstance(value, dict) else value
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value, current_path)
        else:
            result[key] = value
    return result


def _environment_name() -> str:
    environment = os.getenv("DIVISION_OVERTIME_ENV", "production").strip().lower()
    if environment not in _SUPPORTED_ENVIRONMENTS:
        raise ConfigError("DIVISION_OVERTIME_ENV must be development or production")
    return environment


def _load_toml_config(root: Path) -> dict[str, Any]:
    with (root / "config/default.toml").open("rb") as handle:
        raw = tomllib.load(handle)
    override_path = root / "config" / f"{_environment_name()}.toml"
    if override_path.exists():
        with override_path.open("rb") as handle:
            raw = _deep_merge(raw, tomllib.load(handle))
    return raw


def load_config(root: Path | None = None) -> AppConfig:
    root = (root or Path.cwd()).resolve()
    load_dotenv(root / ".env")
    raw = _load_toml_config(root)

    kot_token = os.getenv("KINGOFTIME_TOKEN", "").strip()
    slack_token = os.getenv("SLACK_BOT_TOKEN", "").strip()
    if not kot_token:
        raise ConfigError("KINGOFTIME_TOKEN is not set")
    if not slack_token:
        raise ConfigError("SLACK_BOT_TOKEN is not set")

    app = raw["app"]
    kot = raw["king_of_time"]
    overtime = raw["overtime"]
    notifications = raw["notifications"]
    return AppConfig(
        root=root,
        timezone=ZoneInfo(app["timezone"]),
        database_path=root / app["database_path"],
        employee_csv=root / app["employee_csv"],
        log_level=str(app.get("log_level", "INFO")),
        kot_base_url=kot["base_url"].rstrip("/"),
        kot_endpoint=kot["endpoint"],
        kot_token=kot_token,
        connect_timeout=float(kot["connect_timeout_seconds"]),
        read_timeout=float(kot["read_timeout_seconds"]),
        retry_count=int(kot["retry_count"]),
        retry_backoff=float(kot["retry_backoff_seconds"]),
        default_target_minutes=int(overtime["default_target_minutes"]),
        thresholds=tuple(sorted(int(x) for x in overtime["thresholds"])),
        division_targets={str(k): int(v) for k, v in overtime["division_targets"].items()},
        slack_token=slack_token,
        department_recipients={
            str(k): tuple(str(address) for address in values)
            for k, values in notifications["department_recipients"].items()
        },
        enable_self_notify=bool(notifications.get("enable_self_notify", False)),
        self_notify_employee_codes=frozenset(
            str(code) for code in notifications.get("self_notify_employee_codes", [])
        ),
        force_self_threshold=int(overtime.get("force_self_threshold", 95)),
    )
