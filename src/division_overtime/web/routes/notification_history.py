from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from division_overtime.notification_history import (
    NotificationAttempt,
    NotificationHistoryRepository,
    NotificationHistorySummary,
    NotificationRunDetail,
    NotificationRunNotFoundError,
    NotificationRunSummary,
)
from division_overtime.web.auth import AuthenticatedUser
from division_overtime.web.dependencies import get_current_user

router = APIRouter(prefix="/api/notification-runs", tags=["notification-runs"])


class NotificationAttemptResponse(BaseModel):
    id: int
    dedupeKey: str
    employeeCode: str | None
    employeeName: str | None
    recipient: str
    notificationType: str
    thresholdPercent: int | None
    status: Literal["pending", "sent", "failed", "skipped"]
    attemptCount: int
    slackTimestamp: str | None
    errorMessage: str | None
    createdAt: str
    updatedAt: str
    duplicateOfAttemptId: int | None
    duplicateOfRunId: str | None
    duplicateOfStartedAt: str | None
    duplicateOfSource: Literal["timer", "manual", "test", "unknown"] | None


class NotificationRunResponse(BaseModel):
    runId: str
    mode: Literal["threshold", "weekly", "health"]
    startedAt: str
    finishedAt: str | None
    status: Literal["running", "succeeded", "failed"]
    dryRun: bool
    source: Literal["timer", "manual", "test", "unknown"]
    errorMessage: str | None
    targetCount: int
    attemptCount: int
    sentCount: int
    failedCount: int
    skippedCount: int
    pendingCount: int


class NotificationHistorySummaryResponse(BaseModel):
    total: int
    succeeded: int
    attention: int
    sent: int


class NotificationRunPageResponse(BaseModel):
    items: list[NotificationRunResponse]
    total: int
    limit: int
    offset: int
    summary: NotificationHistorySummaryResponse


class NotificationRunDetailResponse(NotificationRunResponse):
    attempts: list[NotificationAttemptResponse]


def get_notification_history_repository(request: Request) -> NotificationHistoryRepository:
    return request.app.state.notification_history_repository


def _run_response(run: NotificationRunSummary) -> NotificationRunResponse:
    return NotificationRunResponse(
        runId=run.run_id,
        mode=run.mode,
        startedAt=run.started_at,
        finishedAt=run.finished_at,
        status=run.status,
        dryRun=run.dry_run,
        source=run.source,
        errorMessage=run.error_message,
        targetCount=run.target_count,
        attemptCount=run.attempt_count,
        sentCount=run.sent_count,
        failedCount=run.failed_count,
        skippedCount=run.skipped_count,
        pendingCount=run.pending_count,
    )


def _attempt_response(attempt: NotificationAttempt) -> NotificationAttemptResponse:
    return NotificationAttemptResponse(
        id=attempt.id,
        dedupeKey=attempt.dedupe_key,
        employeeCode=attempt.employee_code,
        employeeName=attempt.employee_name,
        recipient=attempt.recipient,
        notificationType=attempt.notification_type,
        thresholdPercent=attempt.threshold_percent,
        status=attempt.status,
        attemptCount=attempt.attempt_count,
        slackTimestamp=attempt.slack_timestamp,
        errorMessage=attempt.error_message,
        createdAt=attempt.created_at,
        updatedAt=attempt.updated_at,
        duplicateOfAttemptId=attempt.duplicate_of_attempt_id,
        duplicateOfRunId=attempt.duplicate_of_run_id,
        duplicateOfStartedAt=attempt.duplicate_of_started_at,
        duplicateOfSource=attempt.duplicate_of_source,
    )


@router.get("", response_model=NotificationRunPageResponse)
def list_notification_runs(
    _: Annotated[AuthenticatedUser, Depends(get_current_user)],
    repository: Annotated[
        NotificationHistoryRepository, Depends(get_notification_history_repository)
    ],
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> NotificationRunPageResponse:
    summary: NotificationHistorySummary = repository.summarize_runs()
    return NotificationRunPageResponse(
        items=[_run_response(run) for run in repository.list_runs(limit=limit, offset=offset)],
        total=summary.total_count,
        limit=limit,
        offset=offset,
        summary=NotificationHistorySummaryResponse(
            total=summary.total_count,
            succeeded=summary.succeeded_count,
            attention=summary.attention_count,
            sent=summary.sent_count,
        ),
    )


@router.get("/{run_id}", response_model=NotificationRunDetailResponse)
def get_notification_run(
    run_id: str,
    _: Annotated[AuthenticatedUser, Depends(get_current_user)],
    repository: Annotated[
        NotificationHistoryRepository, Depends(get_notification_history_repository)
    ],
) -> NotificationRunDetailResponse:
    try:
        detail: NotificationRunDetail = repository.get_run(run_id)
    except NotificationRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification run not found.",
        ) from exc

    run = _run_response(detail.run)
    return NotificationRunDetailResponse(
        **run.model_dump(),
        attempts=[_attempt_response(attempt) for attempt in detail.attempts],
    )
