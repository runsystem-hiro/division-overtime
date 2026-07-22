from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


class WebConfigError(RuntimeError):
    """Raised when the Web application configuration is invalid."""


@dataclass(frozen=True, slots=True)
class WebConfig:
    root: Path
    timezone: ZoneInfo
    database_path: Path
    employee_csv: Path
    frontend_dist: Path
    host: str
    port: int
    log_level: str


def load_web_config(root: Path | None = None) -> WebConfig:
    """Load settings required to start the Web application.

    This loader intentionally does not require KINGOFTIME_TOKEN or
    SLACK_BOT_TOKEN. External-service credentials are loaded only by the
    existing notification commands that need them.
    """

    root = (root or Path.cwd()).resolve()
    load_dotenv(root / ".env")

    default_path = root / "config/default.toml"
    if not default_path.is_file():
        raise WebConfigError(f"configuration file not found: {default_path}")

    with default_path.open("rb") as handle:
        raw = tomllib.load(handle)

    try:
        app = raw["app"]
        timezone = ZoneInfo(str(app["timezone"]))
        database_path = root / str(app["database_path"])
        employee_csv = root / str(app["employee_csv"])
    except (KeyError, TypeError, ValueError) as exc:
        raise WebConfigError("invalid [app] configuration") from exc

    host = os.getenv("WEB_HOST", "0.0.0.0").strip() or "0.0.0.0"
    log_level = os.getenv("WEB_LOG_LEVEL", str(app.get("log_level", "INFO"))).upper()

    try:
        port = int(os.getenv("WEB_PORT", "8000"))
    except ValueError as exc:
        raise WebConfigError("WEB_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise WebConfigError("WEB_PORT must be between 1 and 65535")

    return WebConfig(
        root=root,
        timezone=timezone,
        database_path=database_path,
        employee_csv=employee_csv,
        frontend_dist=root / "frontend/dist",
        host=host,
        port=port,
        log_level=log_level,
    )
