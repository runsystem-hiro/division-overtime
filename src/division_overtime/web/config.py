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
    admin_username: str
    admin_password_hash: str
    session_secret: str
    session_cookie_name: str
    session_cookie_secure: bool
    session_max_age_seconds: int
    login_max_attempts: int
    login_window_seconds: int
    login_lockout_seconds: int
    kot_base_url: str
    kot_token: str
    kot_connect_timeout: float
    kot_read_timeout: float
    kot_retry_count: int
    kot_retry_backoff: float


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise WebConfigError(f"required environment variable is not set: {name}")
    return value


def _positive_int_env(name: str, default: str) -> int:
    try:
        value = int(os.getenv(name, default))
    except ValueError as exc:
        raise WebConfigError(f"{name} must be an integer") from exc
    if value <= 0:
        raise WebConfigError(f"{name} must be greater than 0")
    return value


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise WebConfigError(f"{name} must be true or false")


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

    session_cookie_name = os.getenv("WEB_SESSION_COOKIE_NAME", "division_overtime_session").strip()
    if not session_cookie_name:
        raise WebConfigError("WEB_SESSION_COOKIE_NAME must not be empty")

    session_secret = _required_env("WEB_SESSION_SECRET")
    if len(session_secret) < 32:
        raise WebConfigError("WEB_SESSION_SECRET must be at least 32 characters")

    return WebConfig(
        root=root,
        timezone=timezone,
        database_path=database_path,
        employee_csv=employee_csv,
        frontend_dist=root / "frontend/dist",
        host=host,
        port=port,
        log_level=log_level,
        admin_username=_required_env("WEB_ADMIN_USERNAME"),
        admin_password_hash=_required_env("WEB_ADMIN_PASSWORD_HASH"),
        session_secret=session_secret,
        session_cookie_name=session_cookie_name,
        session_cookie_secure=_bool_env("WEB_SESSION_COOKIE_SECURE", False),
        session_max_age_seconds=_positive_int_env("WEB_SESSION_MAX_AGE_SECONDS", "28800"),
        login_max_attempts=_positive_int_env("WEB_LOGIN_MAX_ATTEMPTS", "5"),
        login_window_seconds=_positive_int_env("WEB_LOGIN_WINDOW_SECONDS", "900"),
        login_lockout_seconds=_positive_int_env("WEB_LOGIN_LOCKOUT_SECONDS", "900"),
        kot_base_url=str(
            raw.get("king_of_time", {}).get("base_url", "https://api.kingtime.jp/v1.0")
        ).rstrip("/"),
        kot_token=os.getenv("KINGOFTIME_TOKEN", "").strip(),
        kot_connect_timeout=float(raw.get("king_of_time", {}).get("connect_timeout_seconds", 5)),
        kot_read_timeout=float(raw.get("king_of_time", {}).get("read_timeout_seconds", 30)),
        kot_retry_count=int(raw.get("king_of_time", {}).get("retry_count", 3)),
        kot_retry_backoff=float(raw.get("king_of_time", {}).get("retry_backoff_seconds", 2)),
    )
