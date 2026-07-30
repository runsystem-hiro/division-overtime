from __future__ import annotations

from dataclasses import dataclass

from division_overtime.database import Database


@dataclass(frozen=True)
class NotificationRunSummary:
    run_id: str
    mode: str
    started_at: str
    finished_at: str | None
    status: str
    dry_run: bool
    source: str
    error_message: str | None
    target_count: int
    attempt_count: int
    sent_count: int
    failed_count: int
    skipped_count: int
    pending_count: int


@dataclass(frozen=True)
class NotificationAttempt:
    id: int
    dedupe_key: str
    employee_code: str | None
    employee_name: str | None
    recipient: str
    notification_type: str
    threshold_percent: int | None
    status: str
    attempt_count: int
    slack_timestamp: str | None
    error_message: str | None
    created_at: str
    updated_at: str
    duplicate_of_attempt_id: int | None
    duplicate_of_run_id: str | None
    duplicate_of_started_at: str | None
    duplicate_of_source: str | None


@dataclass(frozen=True)
class NotificationRunDetail:
    run: NotificationRunSummary
    attempts: tuple[NotificationAttempt, ...]


class NotificationRunNotFoundError(LookupError):
    pass


class NotificationHistoryRepository:
    _RUN_COLUMNS = """
        r.run_id,
        r.mode,
        r.started_at,
        r.finished_at,
        r.status,
        r.dry_run,
        r.source,
        r.error_message,
        (SELECT COUNT(*) FROM overtime_snapshots AS s
         WHERE s.run_id = r.run_id) AS target_count,
        (SELECT COUNT(*) FROM notification_attempts AS a
         WHERE a.run_id = r.run_id) AS attempt_count,
        (SELECT COUNT(*) FROM notification_attempts AS a
         WHERE a.run_id = r.run_id AND a.status = 'sent') AS sent_count,
        (SELECT COUNT(*) FROM notification_attempts AS a
         WHERE a.run_id = r.run_id AND a.status = 'failed') AS failed_count,
        (SELECT COUNT(*) FROM notification_attempts AS a
         WHERE a.run_id = r.run_id AND a.status = 'skipped') AS skipped_count,
        (SELECT COUNT(*) FROM notification_attempts AS a
         WHERE a.run_id = r.run_id AND a.status = 'pending') AS pending_count
    """

    def __init__(self, database: Database):
        self.database = database

    def list_runs(self, *, limit: int, offset: int) -> list[NotificationRunSummary]:
        query = f"""
            SELECT {self._RUN_COLUMNS}
            FROM execution_runs AS r
            ORDER BY r.started_at DESC, r.id DESC
            LIMIT ? OFFSET ?
        """
        with self.database.connect_readonly() as conn:
            rows = conn.execute(query, (limit, offset)).fetchall()
        return [self._run_summary(row) for row in rows]

    def get_run(self, run_id: str) -> NotificationRunDetail:
        query = f"""
            SELECT {self._RUN_COLUMNS}
            FROM execution_runs AS r
            WHERE r.run_id = ?
        """
        with self.database.connect_readonly() as conn:
            run_row = conn.execute(query, (run_id,)).fetchone()
            if run_row is None:
                raise NotificationRunNotFoundError(run_id)

            attempt_rows = conn.execute(
                """
                SELECT
                    a.id,
                    a.dedupe_key,
                    a.employee_code,
                    COALESCE(
                        snapshot.employee_name,
                        NULLIF(TRIM(employee.last_name || ' ' || employee.first_name), '')
                    ) AS employee_name,
                    a.recipient,
                    a.notification_type,
                    a.threshold_percent,
                    a.status,
                    a.attempt_count,
                    a.slack_timestamp,
                    a.error_message,
                    a.created_at,
                    a.updated_at,
                    a.duplicate_of_attempt_id,
                    original.run_id AS duplicate_of_run_id,
                    original_run.started_at AS duplicate_of_started_at,
                    original_run.source AS duplicate_of_source
                FROM notification_attempts AS a
                LEFT JOIN overtime_snapshots AS snapshot
                    ON snapshot.run_id = a.run_id
                    AND snapshot.employee_code = a.employee_code
                LEFT JOIN employees AS employee
                    ON employee.code = a.employee_code
                LEFT JOIN notification_attempts AS original
                    ON original.id = a.duplicate_of_attempt_id
                LEFT JOIN execution_runs AS original_run
                    ON original_run.run_id = original.run_id
                WHERE a.run_id = ?
                ORDER BY a.created_at, a.id
                """,
                (run_id,),
            ).fetchall()

        return NotificationRunDetail(
            run=self._run_summary(run_row),
            attempts=tuple(
                NotificationAttempt(
                    id=int(row["id"]),
                    dedupe_key=str(row["dedupe_key"]),
                    employee_code=row["employee_code"],
                    employee_name=row["employee_name"],
                    recipient=str(row["recipient"]),
                    notification_type=str(row["notification_type"]),
                    threshold_percent=row["threshold_percent"],
                    status=str(row["status"]),
                    attempt_count=int(row["attempt_count"]),
                    slack_timestamp=row["slack_timestamp"],
                    error_message=row["error_message"],
                    created_at=str(row["created_at"]),
                    updated_at=str(row["updated_at"]),
                    duplicate_of_attempt_id=row["duplicate_of_attempt_id"],
                    duplicate_of_run_id=row["duplicate_of_run_id"],
                    duplicate_of_started_at=row["duplicate_of_started_at"],
                    duplicate_of_source=row["duplicate_of_source"],
                )
                for row in attempt_rows
            ),
        )

    @staticmethod
    def _run_summary(row) -> NotificationRunSummary:
        return NotificationRunSummary(
            run_id=str(row["run_id"]),
            mode=str(row["mode"]),
            started_at=str(row["started_at"]),
            finished_at=row["finished_at"],
            status=str(row["status"]),
            dry_run=bool(row["dry_run"]),
            source=str(row["source"]),
            error_message=row["error_message"],
            target_count=int(row["target_count"] or 0),
            attempt_count=int(row["attempt_count"] or 0),
            sent_count=int(row["sent_count"] or 0),
            failed_count=int(row["failed_count"] or 0),
            skipped_count=int(row["skipped_count"] or 0),
            pending_count=int(row["pending_count"] or 0),
        )
