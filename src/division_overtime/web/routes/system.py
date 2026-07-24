from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from division_overtime.web.config import WebConfig
from division_overtime.web.dependencies import get_web_config

router = APIRouter(prefix="/api", tags=["system"])


def _read_version(root: Path) -> str:
    version_path = root / "VERSION"
    if not version_path.is_file():
        return "unknown"
    return version_path.read_text(encoding="utf-8").strip() or "unknown"


@router.get("/system/health")
def system_health(config: Annotated[WebConfig, Depends(get_web_config)]) -> dict[str, object]:
    now = datetime.now(config.timezone)
    return {
        "status": "ok",
        "service": "division-overtime-web",
        "version": _read_version(config.root),
        "serverTime": now.isoformat(),
        "timezone": str(config.timezone),
        "frontendBuilt": config.frontend_dist.is_dir(),
        "environment": config.environment,
        "kotSyncEnabled": config.kot_enabled,
    }


@router.get("/version")
def version(config: Annotated[WebConfig, Depends(get_web_config)]) -> dict[str, str]:
    return {"version": _read_version(config.root)}
