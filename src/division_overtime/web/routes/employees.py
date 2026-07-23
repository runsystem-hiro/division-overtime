from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator

from division_overtime.employee_management import (
    EmployeeChange,
    EmployeeConflictError,
    EmployeeManagementError,
    EmployeeManagementService,
    EmployeeNotFoundError,
)
from division_overtime.employee_repository import ManagedEmployee
from division_overtime.web.auth import AuthenticatedUser
from division_overtime.web.config import WebConfig
from division_overtime.web.dependencies import get_current_user, get_web_config

router = APIRouter(prefix="/api/employees", tags=["employees"])


class EmployeeResponse(BaseModel):
    code: str
    lastName: str
    firstName: str
    fullName: str
    email: str
    divisionCode: str
    divisionName: str
    personalTargetMinutes: int | None
    isEnabled: bool
    disabledReason: str
    note: str
    kotExists: bool
    createdAt: str
    updatedAt: str


class EmployeeWriteRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    employeeKey: str | None = Field(default=None, max_length=512)
    lastName: str = Field(min_length=1, max_length=128)
    firstName: str = Field(min_length=1, max_length=128)
    email: str = Field(default="", max_length=320)
    divisionCode: str = Field(min_length=1, max_length=128)
    divisionName: str = Field(default="", max_length=256)
    personalTargetMinutes: int | None = Field(default=None, ge=0)
    isEnabled: bool = True
    disabledReason: str = Field(default="", max_length=512)
    note: str = Field(default="", max_length=2000)

    @field_validator(
        "code",
        "employeeKey",
        "lastName",
        "firstName",
        "email",
        "divisionCode",
        "divisionName",
        "disabledReason",
        "note",
        mode="before",
    )
    @classmethod
    def strip_strings(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


def get_employee_service(request: Request) -> EmployeeManagementService:
    return request.app.state.employee_management_service


def _response(employee: ManagedEmployee) -> EmployeeResponse:
    return EmployeeResponse(
        code=employee.code,
        lastName=employee.last_name,
        firstName=employee.first_name,
        fullName=employee.full_name,
        email=employee.email,
        divisionCode=employee.division_code,
        divisionName=employee.division_name,
        personalTargetMinutes=employee.personal_target_minutes,
        isEnabled=employee.is_enabled,
        disabledReason=employee.disabled_reason,
        note=employee.note,
        kotExists=employee.kot_exists,
        createdAt=employee.created_at,
        updatedAt=employee.updated_at,
    )


def _change(payload: EmployeeWriteRequest) -> EmployeeChange:
    return EmployeeChange(
        code=payload.code,
        employee_key=payload.employeeKey,
        last_name=payload.lastName,
        first_name=payload.firstName,
        email=payload.email,
        division_code=payload.divisionCode,
        division_name=payload.divisionName,
        personal_target_minutes=payload.personalTargetMinutes,
        is_enabled=payload.isEnabled,
        disabled_reason=payload.disabledReason,
        note=payload.note,
    )


def _raise_http_error(exc: EmployeeManagementError) -> None:
    if isinstance(exc, EmployeeNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, EmployeeConflictError):
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.get("", response_model=list[EmployeeResponse])
def list_employees(
    _: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[EmployeeManagementService, Depends(get_employee_service)],
    query: str = Query(default="", max_length=128),
    enabled: Literal["all", "enabled", "disabled"] = "all",
) -> list[EmployeeResponse]:
    enabled_value = None if enabled == "all" else enabled == "enabled"
    return [
        _response(employee)
        for employee in service.list_employees(query=query, enabled=enabled_value)
    ]


@router.get("/{code}", response_model=EmployeeResponse)
def get_employee(
    code: str,
    _: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[EmployeeManagementService, Depends(get_employee_service)],
) -> EmployeeResponse:
    try:
        return _response(service.get_employee(code))
    except EmployeeManagementError as exc:
        _raise_http_error(exc)


@router.post("", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
def create_employee(
    payload: EmployeeWriteRequest,
    _: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[EmployeeManagementService, Depends(get_employee_service)],
    config: Annotated[WebConfig, Depends(get_web_config)],
) -> EmployeeResponse:
    try:
        employee = service.create_employee(_change(payload), datetime.now(config.timezone))
        return _response(employee)
    except EmployeeManagementError as exc:
        _raise_http_error(exc)


@router.put("/{code}", response_model=EmployeeResponse)
def update_employee(
    code: str,
    payload: EmployeeWriteRequest,
    _: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[EmployeeManagementService, Depends(get_employee_service)],
    config: Annotated[WebConfig, Depends(get_web_config)],
) -> EmployeeResponse:
    try:
        employee = service.update_employee(code, _change(payload), datetime.now(config.timezone))
        return _response(employee)
    except EmployeeManagementError as exc:
        _raise_http_error(exc)
