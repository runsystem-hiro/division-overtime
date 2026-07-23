from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from division_overtime.kot_employee_sync import (
    KotEmployeeSyncError,
    KotEmployeeSyncService,
    SyncDifference,
)
from division_overtime.web.auth import AuthenticatedUser
from division_overtime.web.config import WebConfig
from division_overtime.web.dependencies import get_current_user, get_web_config

router = APIRouter(prefix="/api/kot-sync", tags=["kot-sync"])


class ApplyRequest(BaseModel):
    previewId: str = Field(min_length=1, max_length=128)
    employeeCodes: list[str] = Field(min_length=1, max_length=500)


def get_service(request: Request) -> KotEmployeeSyncService:
    service = getattr(request.app.state, "kot_employee_sync_service", None)
    if service is None:
        raise HTTPException(
            status_code=503, detail="KOT employee synchronization is not configured"
        )
    return service


def _diff(diff: SyncDifference) -> dict[str, object]:
    return {
        "code": diff.code,
        "action": diff.action,
        "current": diff.current,
        "proposed": diff.proposed,
        "warnings": list(diff.warnings),
    }


@router.post("/preview")
def preview(
    _: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[KotEmployeeSyncService, Depends(get_service)],
) -> dict[str, object]:
    try:
        preview_id, differences = service.preview()
    except KotEmployeeSyncError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    counts = {
        name: sum(item.action == name for item in differences)
        for name in ("create", "update", "disable", "unchanged")
    }
    metadata = service.preview_metadata(preview_id)
    return {
        "previewId": preview_id,
        "counts": counts,
        "differences": [_diff(item) for item in differences],
        **metadata,
    }


@router.post("/apply")
def apply(
    payload: ApplyRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[KotEmployeeSyncService, Depends(get_service)],
    config: Annotated[WebConfig, Depends(get_web_config)],
) -> dict[str, object]:
    try:
        counts = service.apply(
            payload.previewId, payload.employeeCodes, user.username, datetime.now(config.timezone)
        )
    except KotEmployeeSyncError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "counts": counts}


@router.get("/history")
def history(
    _: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[KotEmployeeSyncService, Depends(get_service)],
) -> list[dict[str, object]]:
    return service.history()
