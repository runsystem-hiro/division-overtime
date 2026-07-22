from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from division_overtime.web.auth import AuthenticatedUser, AuthService
from division_overtime.web.config import WebConfig


def get_web_config(request: Request) -> WebConfig:
    return request.app.state.web_config


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


def get_current_user(
    request: Request,
    config: Annotated[WebConfig, Depends(get_web_config)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthenticatedUser:
    user = auth.get_user(request.cookies.get(config.session_cookie_name))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required."
        )
    return user
