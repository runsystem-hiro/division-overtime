from pathlib import Path

from division_overtime.database import Database
from division_overtime.database_observability import observe_database


def test_observe_database_reports_sizes_counts_and_integrity(tmp_path: Path) -> None:
    db = Database(tmp_path / "division_overtime.sqlite3")
    db.initialize()
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO execution_runs("
            "run_id,mode,started_at,status,dry_run,source"
            ") VALUES('run-1','weekly','2026-07-25T15:00:00+09:00',"
            "'succeeded',0,'timer')"
        )
        conn.execute(
            "INSERT INTO notification_attempts("
            "dedupe_key,run_id,employee_code,recipient,notification_type,status,"
            "attempt_count,created_at,updated_at"
            ") VALUES('weekly:2026-W30:00001','run-1','00001','a@example.com',"
            "'weekly','sent',1,'now','now')"
        )

    observation = observe_database(db)

    assert observation.database_path == db.path
    assert observation.database_bytes > 0
    assert observation.total_bytes >= observation.database_bytes
    assert observation.table_counts["execution_runs"] == 1
    assert observation.table_counts["notification_attempts"] == 1
    assert observation.table_counts["employees"] == 0
    assert observation.table_counts["kot_sync_runs"] == 0
    assert observation.notification_attempt_counts == {"sent": 1}
    assert observation.integrity_check == "ok"
