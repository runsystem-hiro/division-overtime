from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from division_overtime.web.auth import AuthenticatedUser, AuthService
from division_overtime.web.cloudflare_access import CloudflareIdentity
from division_overtime.web.config import WebConfig
from division_overtime.web.dependencies import (
    get_auth_service,
    get_cloudflare_identity,
    get_current_user,
    get_optional_current_user,
    get_web_config,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


class ElevateRequest(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


def _rate_limit_key(request: Request, scope: str = "login") -> str:
    host = request.client.host if request.client else "unknown"
    return f"{scope}:{host}"


def _set_session_cookie(response: Response, config: WebConfig, token: str, max_age: int) -> None:
    response.set_cookie(
        key=config.session_cookie_name,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=config.session_cookie_secure,
        samesite="strict",
        path="/",
    )


def _user_response(user: AuthenticatedUser, config: WebConfig) -> dict[str, object]:
    return {
        "username": user.username,
        "role": user.role,
        "expiresAt": user.expires_at.isoformat(),
        "identitySource": user.identity_source,
        "elevatedUntil": user.elevated_until.isoformat() if user.elevated_until else None,
        "logoutUrl": (
            config.cloudflare_access_logout_url
            if user.identity_source == "cloudflare_access"
            else None
        ),
    }


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    config: Annotated[WebConfig, Depends(get_web_config)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> dict[str, object]:
    now = datetime.now(UTC)
    key = _rate_limit_key(request)
    if auth.rate_limiter.is_blocked(key, now):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
        )

    role = auth.authenticate(payload.username, payload.password)
    if role is None:
        auth.rate_limiter.record_failure(key, now)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    auth.rate_limiter.clear(key)
    token, expires_at = auth.create_session(payload.username, now, role=role)
    _set_session_cookie(response, config, token, config.session_max_age_seconds)
    return _user_response(AuthenticatedUser(payload.username, role, expires_at), config)


@router.post("/elevate")
def elevate(
    payload: ElevateRequest,
    request: Request,
    response: Response,
    config: Annotated[WebConfig, Depends(get_web_config)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    identity: Annotated[CloudflareIdentity | None, Depends(get_cloudflare_identity)],
) -> dict[str, object]:
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator elevation is available through Cloudflare Access only.",
        )
    now = datetime.now(UTC)
    key = _rate_limit_key(request, "elevate")
    if auth.rate_limiter.is_blocked(key, now):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many administrator authentication attempts. Try again later.",
        )
    if not auth.authenticate_admin_password(payload.password):
        auth.rate_limiter.record_failure(key, now)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password.")

    auth.rate_limiter.clear(key)
    elevated_until = min(
        now + timedelta(minutes=config.admin_elevation_minutes), identity.expires_at
    )
    token, expires_at = auth.create_session(
        identity.email,
        now,
        role="admin",
        identity_source="cloudflare_access",
        expires_at_limit=identity.expires_at,
        elevated_until=elevated_until,
    )
    max_age = max(1, int((expires_at - now).total_seconds()))
    _set_session_cookie(response, config, token, max_age)
    return _user_response(
        AuthenticatedUser(
            identity.email,
            "admin",
            expires_at,
            identity_source="cloudflare_access",
            elevated_until=elevated_until,
        ),
        config,
    )


@router.post("/downgrade")
def downgrade(
    request: Request,
    response: Response,
    config: Annotated[WebConfig, Depends(get_web_config)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    identity: Annotated[CloudflareIdentity | None, Depends(get_cloudflare_identity)],
) -> dict[str, object]:
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access identity required."
        )
    auth.delete_session(request.cookies.get(config.session_cookie_name))
    response.delete_cookie(
        key=config.session_cookie_name,
        path="/",
        secure=config.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return _user_response(
        AuthenticatedUser(
            identity.email,
            "viewer",
            identity.expires_at,
            identity_source="cloudflare_access",
        ),
        config,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    config: Annotated[WebConfig, Depends(get_web_config)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    auth.delete_session(request.cookies.get(config.session_cookie_name))
    response.delete_cookie(
        key=config.session_cookie_name,
        path="/",
        secure=config.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )


@router.get("/status")
def auth_status(
    config: Annotated[WebConfig, Depends(get_web_config)],
    user: Annotated[AuthenticatedUser | None, Depends(get_optional_current_user)],
) -> dict[str, object]:
    if user is None:
        return {"authenticated": False, "user": None}
    return {"authenticated": True, "user": _user_response(user, config)}


@router.get("/me")
def me(
    config: Annotated[WebConfig, Depends(get_web_config)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> dict[str, object]:
    return _user_response(user, config)
