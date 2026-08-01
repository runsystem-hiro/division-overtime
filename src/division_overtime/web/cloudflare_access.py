from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError


class CloudflareAccessError(RuntimeError):
    """Raised when a Cloudflare Access assertion cannot be verified."""


@dataclass(frozen=True, slots=True)
class CloudflareIdentity:
    email: str
    expires_at: datetime


class CloudflareAccessVerifier:
    def __init__(self, *, team_domain: str, audience: str) -> None:
        normalized_domain = team_domain.strip().removeprefix("https://").rstrip("/")
        normalized_audience = audience.strip()
        if not normalized_domain or not normalized_audience:
            raise ValueError("team_domain and audience are required")

        self._issuer = f"https://{normalized_domain}"
        self._audience = normalized_audience
        self._jwk_client = PyJWKClient(
            f"{self._issuer}/cdn-cgi/access/certs",
            cache_keys=True,
            lifespan=300,
        )

    def verify(self, token: str) -> CloudflareIdentity:
        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iss", "aud", "email"]},
            )
        except (PyJWTError, ValueError, TypeError) as exc:
            raise CloudflareAccessError("Cloudflare Access assertion is invalid") from exc

        email = claims.get("email")
        expires_at = claims.get("exp")
        if not isinstance(email, str) or not email.strip():
            raise CloudflareAccessError("Cloudflare Access email claim is invalid")
        if not isinstance(expires_at, int | float):
            raise CloudflareAccessError("Cloudflare Access exp claim is invalid")

        try:
            expires_at_datetime = datetime.fromtimestamp(expires_at, tz=UTC)
        except (OverflowError, OSError, ValueError) as exc:
            raise CloudflareAccessError("Cloudflare Access exp claim is invalid") from exc

        return CloudflareIdentity(email=email.strip(), expires_at=expires_at_datetime)
