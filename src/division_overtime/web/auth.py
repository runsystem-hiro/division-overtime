from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

UserRole = Literal["admin", "viewer"]


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    username: str
    role: UserRole
    expires_at: datetime
    identity_source: str = "local"
    elevated_until: datetime | None = None


@dataclass(slots=True)
class _Session:
    username: str
    role: UserRole
    expires_at: datetime
    identity_source: str = "local"
    elevated_until: datetime | None = None


class LoginRateLimiter:
    def __init__(self, *, max_attempts: int, window_seconds: int, lockout_seconds: int) -> None:
        self._max_attempts = max_attempts
        self._window = timedelta(seconds=window_seconds)
        self._lockout = timedelta(seconds=lockout_seconds)
        self._attempts: dict[str, deque[datetime]] = defaultdict(deque)
        self._locked_until: dict[str, datetime] = {}
        self._lock = threading.Lock()

    def is_blocked(self, key: str, now: datetime) -> bool:
        with self._lock:
            locked_until = self._locked_until.get(key)
            if locked_until is None:
                return False
            if now >= locked_until:
                self._locked_until.pop(key, None)
                self._attempts.pop(key, None)
                return False
            return True

    def record_failure(self, key: str, now: datetime) -> None:
        with self._lock:
            attempts = self._attempts[key]
            cutoff = now - self._window
            while attempts and attempts[0] < cutoff:
                attempts.popleft()
            attempts.append(now)
            if len(attempts) >= self._max_attempts:
                self._locked_until[key] = now + self._lockout
                attempts.clear()

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)
            self._locked_until.pop(key, None)


class AuthService:
    def __init__(
        self,
        *,
        admin_username: str,
        admin_password_hash: str,
        session_secret: str,
        session_max_age_seconds: int,
        login_max_attempts: int,
        login_window_seconds: int,
        login_lockout_seconds: int,
        viewer_username: str | None = None,
        viewer_password_hash: str | None = None,
    ) -> None:
        self._admin_username = admin_username
        self._admin_password_hash = admin_password_hash
        self._viewer_username = viewer_username
        self._viewer_password_hash = viewer_password_hash
        self._secret = session_secret.encode("utf-8")
        self._session_max_age = timedelta(seconds=session_max_age_seconds)
        self._sessions: dict[str, _Session] = {}
        self._lock = threading.Lock()
        self._password_hasher = PasswordHasher()
        self.rate_limiter = LoginRateLimiter(
            max_attempts=login_max_attempts,
            window_seconds=login_window_seconds,
            lockout_seconds=login_lockout_seconds,
        )

    def authenticate(self, username: str, password: str) -> UserRole | None:
        credentials: tuple[tuple[UserRole, str, str], ...] = (
            ("admin", self._admin_username, self._admin_password_hash),
        )
        if self._viewer_username is not None and self._viewer_password_hash is not None:
            credentials += (("viewer", self._viewer_username, self._viewer_password_hash),)

        authenticated_role: UserRole | None = None
        for role, configured_username, configured_password_hash in credentials:
            username_matches = hmac.compare_digest(username, configured_username)
            try:
                password_matches = self._password_hasher.verify(configured_password_hash, password)
            except (InvalidHashError, VerificationError, VerifyMismatchError):
                password_matches = False
            if username_matches and password_matches:
                authenticated_role = role
        return authenticated_role

    def authenticate_admin_password(self, password: str) -> bool:
        try:
            return self._password_hasher.verify(self._admin_password_hash, password)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return False

    def create_session(
        self,
        username: str,
        now: datetime | None = None,
        *,
        role: UserRole = "admin",
        identity_source: str = "local",
        expires_at_limit: datetime | None = None,
        elevated_until: datetime | None = None,
    ) -> tuple[str, datetime]:
        now = now or datetime.now(UTC)
        raw_token = secrets.token_urlsafe(48)
        token_digest = self._digest(raw_token)
        expires_at = now + self._session_max_age
        if expires_at_limit is not None:
            expires_at = min(expires_at, expires_at_limit)
        with self._lock:
            self._purge_expired(now)
            self._sessions[token_digest] = _Session(
                username=username,
                role=role,
                expires_at=expires_at,
                identity_source=identity_source,
                elevated_until=elevated_until,
            )
        return raw_token, expires_at

    def get_user(
        self, raw_token: str | None, now: datetime | None = None
    ) -> AuthenticatedUser | None:
        if not raw_token:
            return None
        now = now or datetime.now(UTC)
        token_digest = self._digest(raw_token)
        with self._lock:
            self._purge_expired(now)
            session = self._sessions.get(token_digest)
            if session is None or session.expires_at <= now:
                return None
            role = session.role
            elevated_until = session.elevated_until
            if role == "admin" and elevated_until is not None and elevated_until <= now:
                role = "viewer"
                elevated_until = None
            return AuthenticatedUser(
                username=session.username,
                role=role,
                expires_at=session.expires_at,
                identity_source=session.identity_source,
                elevated_until=elevated_until,
            )

    def delete_session(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        with self._lock:
            self._sessions.pop(self._digest(raw_token), None)

    def _digest(self, raw_token: str) -> str:
        return hmac.new(self._secret, raw_token.encode("utf-8"), hashlib.sha256).hexdigest()

    def _purge_expired(self, now: datetime) -> None:
        expired = [key for key, session in self._sessions.items() if session.expires_at <= now]
        for key in expired:
            self._sessions.pop(key, None)
