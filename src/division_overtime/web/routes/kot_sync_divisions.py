from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from division_overtime.kot_sync_division_repository import (
    KotSyncDivision,
    KotSyncDivisionConflictError,
    KotSyncDivisionError,
    KotSyncDivisionNotFoundError,
    KotSyncDivisionRepository,
)
from division_overtime.web.auth import AuthenticatedUser
from division_overtime.web.dependencies import get_current_admin_user

router = APIRouter(prefix="/api/settings/kot-sync-divisions", tags=["settings"])


class CreateDivisionRequest(BaseModel):
    divisionCode: str = Field(min_length=1, max_length=64)


class UpdateDivisionRequest(BaseModel):
    isEnabled: bool


def get_repository(request: Request) -> KotSyncDivisionRepository:
    return request.app.state.kot_sync_division_repository


def _response(item: KotSyncDivision) -> dict[str, object]:
    return {
        "divisionCode": item.division_code,
        "isEnabled": item.is_enabled,
        "createdAt": item.created_at,
        "updatedAt": item.updated_at,
    }


def _raise(exc: KotSyncDivisionError) -> None:
    if isinstance(exc, KotSyncDivisionNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, KotSyncDivisionConflictError):
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.get("")
def list_divisions(
    _: Annotated[AuthenticatedUser, Depends(get_current_admin_user)],
    repository: Annotated[KotSyncDivisionRepository, Depends(get_repository)],
) -> list[dict[str, object]]:
    return [_response(item) for item in repository.list_all()]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_division(
    payload: CreateDivisionRequest,
    _: Annotated[AuthenticatedUser, Depends(get_current_admin_user)],
    repository: Annotated[KotSyncDivisionRepository, Depends(get_repository)],
) -> dict[str, object]:
    try:
        return _response(repository.create(payload.divisionCode))
    except KotSyncDivisionError as exc:
        _raise(exc)


@router.put("/{division_code}")
def update_division(
    division_code: str,
    payload: UpdateDivisionRequest,
    _: Annotated[AuthenticatedUser, Depends(get_current_admin_user)],
    repository: Annotated[KotSyncDivisionRepository, Depends(get_repository)],
) -> dict[str, object]:
    try:
        return _response(repository.set_enabled(division_code, payload.isEnabled))
    except KotSyncDivisionError as exc:
        _raise(exc)


@router.delete("/{division_code}")
def delete_division(
    division_code: str,
    _: Annotated[AuthenticatedUser, Depends(get_current_admin_user)],
    repository: Annotated[KotSyncDivisionRepository, Depends(get_repository)],
) -> dict[str, object]:
    try:
        return {"deletedDivision": _response(repository.delete(division_code))}
    except KotSyncDivisionError as exc:
        _raise(exc)
