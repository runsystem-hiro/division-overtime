from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from division_overtime.web.auth import AuthenticatedUser, AuthService
from division_overtime.web.config import WebConfig
from division_overtime.web.dependencies import get_auth_service, get_current_user, get_web_config

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


def _rate_limit_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


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

    if not auth.authenticate(payload.username, payload.password):
        auth.rate_limiter.record_failure(key, now)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    auth.rate_limiter.clear(key)
    token, expires_at = auth.create_session(payload.username, now)
    response.set_cookie(
        key=config.session_cookie_name,
        value=token,
        max_age=config.session_max_age_seconds,
        httponly=True,
        secure=config.session_cookie_secure,
        samesite="strict",
        path="/",
    )
    return {"username": payload.username, "expiresAt": expires_at.isoformat()}


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


@router.get("/me")
def me(user: Annotated[AuthenticatedUser, Depends(get_current_user)]) -> dict[str, str]:
    return {"username": user.username, "expiresAt": user.expires_at.isoformat()}
