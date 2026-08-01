from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from division_overtime.web.auth import AuthenticatedUser, AuthService
from division_overtime.web.cloudflare_access import (
    CloudflareAccessError,
    CloudflareAccessVerifier,
    CloudflareIdentity,
)
from division_overtime.web.config import WebConfig


def get_web_config(request: Request) -> WebConfig:
    return request.app.state.web_config


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


def get_cloudflare_access_verifier(request: Request) -> CloudflareAccessVerifier | None:
    return request.app.state.cloudflare_access_verifier


def get_cloudflare_identity(
    request: Request,
    verifier: Annotated[CloudflareAccessVerifier | None, Depends(get_cloudflare_access_verifier)],
) -> CloudflareIdentity | None:
    token = request.headers.get("Cf-Access-Jwt-Assertion")
    if not token:
        return None
    if verifier is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Access is not enabled."
        )
    try:
        return verifier.verify(token)
    except CloudflareAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cloudflare Access authentication failed.",
        ) from exc


def get_optional_current_user(
    request: Request,
    config: Annotated[WebConfig, Depends(get_web_config)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    cloudflare_identity: Annotated[CloudflareIdentity | None, Depends(get_cloudflare_identity)],
) -> AuthenticatedUser | None:
    session_user = auth.get_user(request.cookies.get(config.session_cookie_name))
    if session_user is not None:
        if session_user.identity_source == "cloudflare_access" and (
            cloudflare_identity is None or cloudflare_identity.email != session_user.username
        ):
            return None
        return session_user
    if cloudflare_identity is None:
        return None
    return AuthenticatedUser(
        username=cloudflare_identity.email,
        role="viewer",
        expires_at=cloudflare_identity.expires_at,
        identity_source="cloudflare_access",
    )


def get_current_user(
    user: Annotated[AuthenticatedUser | None, Depends(get_optional_current_user)],
) -> AuthenticatedUser:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required."
        )
    return user


def get_current_admin_user(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Administrator privileges required."
        )
    if user.elevated_until is not None and user.elevated_until <= datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Administrator elevation expired."
        )
    return user
