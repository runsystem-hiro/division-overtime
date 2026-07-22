from __future__ import annotations

from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher

from division_overtime.web.auth import AuthService


def _service(max_age: int = 60) -> AuthService:
    return AuthService(
        admin_username="hiro",
        admin_password_hash=PasswordHasher().hash("secret"),
        session_secret="s" * 48,
        session_max_age_seconds=max_age,
        login_max_attempts=5,
        login_window_seconds=900,
        login_lockout_seconds=900,
    )


def test_session_expires():
    service = _service(max_age=10)
    now = datetime(2026, 7, 22, tzinfo=UTC)
    token, _ = service.create_session("hiro", now)

    assert service.get_user(token, now + timedelta(seconds=9)) is not None
    assert service.get_user(token, now + timedelta(seconds=10)) is None


def test_session_token_is_revoked():
    service = _service()
    token, _ = service.create_session("hiro")
    assert service.get_user(token) is not None
    service.delete_session(token)
    assert service.get_user(token) is None
