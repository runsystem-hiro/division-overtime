from __future__ import annotations

from datetime import datetime, time
from threading import Lock
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
_operation_lock = Lock()


def _is_api_blocked(now: datetime) -> bool:
    current = now.timetz().replace(tzinfo=None)
    return time(8, 30) <= current < time(10, 0) or time(17, 30) <= current < time(18, 30)


def _acquire_operation() -> None:
    if not _operation_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409, detail="KOT employee synchronization is already running"
        )


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
        "changedFields": list(diff.changed_fields),
    }


@router.post("/preview")
def preview(
    _: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[KotEmployeeSyncService, Depends(get_service)],
    config: Annotated[WebConfig, Depends(get_web_config)],
) -> dict[str, object]:
    now = datetime.now(config.timezone)
    if _is_api_blocked(now):
        raise HTTPException(
            status_code=423,
            detail=("KING OF TIME API is unavailable during 08:30-10:00 and 17:30-18:30 JST"),
        )
    _acquire_operation()
    try:
        preview_id, differences = service.preview()
    except KotEmployeeSyncError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        _operation_lock.release()
    counts = {
        name: sum(item.action == name for item in differences)
        for name in ("create", "update", "reactivate", "disable", "unchanged")
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
    now = datetime.now(config.timezone)
    if _is_api_blocked(now):
        raise HTTPException(
            status_code=423,
            detail=("KING OF TIME API is unavailable during 08:30-10:00 and 17:30-18:30 JST"),
        )
    _acquire_operation()
    try:
        counts = service.apply(payload.previewId, payload.employeeCodes, user.username, now)
    except KotEmployeeSyncError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        _operation_lock.release()
    backup_path = str(counts.pop("backupPath"))
    return {"status": "ok", "counts": counts, "backupPath": backup_path}


@router.get("/history")
def history(
    _: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[KotEmployeeSyncService, Depends(get_service)],
) -> list[dict[str, object]]:
    return service.history()


@router.get("/status")
def status(
    _: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[KotEmployeeSyncService, Depends(get_service)],
    config: Annotated[WebConfig, Depends(get_web_config)],
) -> dict[str, object]:
    history = service.history(limit=1)
    return {
        "running": _operation_lock.locked(),
        "blocked": _is_api_blocked(datetime.now(config.timezone)),
        "lastRun": history[0] if history else None,
    }
