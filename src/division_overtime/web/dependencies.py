from __future__ import annotations

from fastapi import Request

from division_overtime.web.config import WebConfig


def get_web_config(request: Request) -> WebConfig:
    return request.app.state.web_config
