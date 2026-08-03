from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

from .backup_observability import BackupObservation, observe_automatic_backups
from .backup_retention import AUTOMATIC_BACKUP_RETENTION, prune_backup_directories
from .config import ConfigError, load_config, load_database_path, load_employee_csv_path
from .database import SCHEMA_VERSION, Database
from .database_observability import DatabaseObservation, observe_database
from .employee_consistency import (
    EmployeeConsistencyResult,
    check_employee_data_consistency,
)
from .employee_repository import EmployeeRepository
from .employees import EmployeeDataError, generate_employee_csv, load_employees
from .service import run

logger = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="division-overtime")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("mode", choices=["threshold", "weekly"])
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument(
        "--source",
        choices=["timer", "manual", "test"],
        default="manual",
        help="execution source recorded in notification history",
    )
    sub.add_parser("health")
    backups_parser = sub.add_parser("backups")
    backups_parser.add_argument("action", choices=["status"])
    db_parser = sub.add_parser("database")
    db_parser.add_argument("action", choices=["init", "migrate", "status", "backup"])
    db_parser.add_argument(
        "--path",
        type=Path,
        help="SQLite path; relative paths are resolved from --root",
    )
    db_parser.add_argument(
        "--output",
        type=Path,
        help="backup output path; valid only for database backup",
    )
    employees_parser = sub.add_parser("employees")
    employees_parser.add_argument(
        "action",
        choices=[
            "import-csv",
            "export-csv",
            "check-consistency",
            "record-consistency",
        ],
    )
    employees_parser.add_argument("--apply", action="store_true")
    employees_parser.add_argument("--json", action="store_true", dest="json_output")
    sub.add_parser("validate-config")
    return parser


def _resolve_path(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root.resolve() / path


def _database_for_args(root: Path, path: Path | None) -> Database:
    database_path = _resolve_path(root, path) if path else load_database_path(root)
    return Database(database_path)


def _default_backup_path(root: Path, now: datetime, category: str = "manual-database") -> Path:
    timestamp = now.strftime("%Y%m%d_%H%M%S_%f")
    return root.resolve() / "var" / "backups" / category / timestamp / "division_overtime.sqlite3"


def _print_database_observation(observation: DatabaseObservation) -> None:
    print(f"database={observation.database_path}")
    print(f"database_bytes={observation.database_bytes}")
    print(f"wal_bytes={observation.wal_bytes}")
    print(f"shm_bytes={observation.shm_bytes}")
    print(f"total_bytes={observation.total_bytes}")
    for table, count in observation.table_counts.items():
        print(f"table_count.{table}={count}")
    for status, count in observation.notification_attempt_counts.items():
        print(f"notification_attempt_count.{status}={count}")
    print(f"employee_count.database_total={observation.employee_total_count}")
    print(f"employee_count.database_enabled={observation.employee_enabled_count}")
    print(f"employee_count.database_disabled={observation.employee_disabled_count}")
    print(f"integrity_check={observation.integrity_check}")


def _print_backup_observation(observation: BackupObservation) -> None:
    prefix = f"backup.{observation.name}"
    print(f"{prefix}.count={observation.count}")
    print(f"{prefix}.retention={observation.retention}")
    print(f"{prefix}.latest={observation.latest or 'none'}")
    print(f"{prefix}.ignored={observation.ignored_count}")
    print(f"{prefix}.status={observation.status}")


def _run_backups_command(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    observations = observe_automatic_backups(
        database_path=load_database_path(root),
        employee_csv=load_employee_csv_path(root),
    )
    for observation in observations:
        _print_backup_observation(observation)
    return 0


def _run_database_command(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    database = _database_for_args(root, args.path)

    if args.action == "init":
        if args.output is not None:
            raise ValueError("--output is valid only for 'database backup' or 'database migrate'")
        database.initialize()
        print(f"database_initialized={database.path}")
        return 0

    if args.action == "migrate":
        before_version = database.schema_version_readonly()
        if before_version > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema version {before_version} is newer than "
                f"supported version {SCHEMA_VERSION}"
            )
        destination = (
            _resolve_path(root, args.output)
            if args.output is not None
            else _default_backup_path(root, datetime.now().astimezone(), "deploy-database")
        )
        if destination.resolve() == database.path.resolve():
            raise ValueError("Backup output must differ from the source database")
        database.backup_to(destination)
        print(f"database_migration_backup=ok source={database.path} output={destination}")
        print(f"schema_version_before={before_version}")
        database.initialize()
        after_version = database.schema_version_readonly()
        integrity = database.integrity_check()
        if integrity != "ok":
            raise RuntimeError(f"Database integrity check failed after migration: {integrity}")
        print(f"schema_version_after={after_version}")
        print("database_migration=ok")
        print("integrity_check=ok")
        if args.output is None:
            backup_root = destination.parent.parent
            try:
                prune_result = prune_backup_directories(
                    backup_root,
                    required_filenames=frozenset({destination.name}),
                )
                print(
                    "database_migration_backup_prune=ok "
                    f"retention={AUTOMATIC_BACKUP_RETENTION} "
                    f"removed={prune_result.removed_count} "
                    f"retained={prune_result.retained_count}"
                )
            except Exception:
                logger.warning(
                    "database_migration_backup_prune=failed backup_root=%s retention=%d",
                    backup_root,
                    AUTOMATIC_BACKUP_RETENTION,
                    exc_info=True,
                )
        return 0

    if args.output is not None and args.action != "backup":
        raise ValueError("--output is valid only for 'database backup' or 'database migrate'")
    if not database.is_initialized_readonly():
        raise RuntimeError(f"Database is not initialized: {database.path}")

    if args.action == "status":
        _print_database_observation(observe_database(database))
        return 0

    destination = (
        _resolve_path(root, args.output)
        if args.output is not None
        else _default_backup_path(root, datetime.now().astimezone())
    )
    if destination.resolve() == database.path.resolve():
        raise ValueError("Backup output must differ from the source database")
    database.backup_to(destination)
    print(f"database_backup=ok source={database.path} output={destination}")
    print("integrity_check=ok")
    return 0


def _import_employees(db: Database, employee_csv: Path, apply: bool) -> int:
    employees = load_employees(employee_csv)
    if not apply:
        print(f"employee_csv_import=preview employees={len(employees)}")
        print("database_changes=none")
        return 0
    if not db.is_initialized():
        raise RuntimeError(
            "Database is not initialized. Run 'division-overtime --root . database init' first."
        )
    repository = EmployeeRepository(db)
    repository.upsert_many(employees, datetime.now().astimezone())
    print(f"employee_csv_import=applied employees={len(employees)}")
    return 0


def _export_employees(db: Database, employee_csv: Path, apply: bool) -> int:
    if not db.is_initialized():
        raise RuntimeError(
            "Database is not initialized. Run 'division-overtime --root . database init' first."
        )
    repository = EmployeeRepository(db)
    employees = repository.list_enabled()
    if not employees:
        raise EmployeeDataError("No enabled employees found; employee CSV was not changed")
    if not apply:
        print(f"employee_csv_export=preview employees={len(employees)}")
        print("csv_changes=none")
        return 0

    result = generate_employee_csv(employee_csv, employees)
    print(
        "employee_csv_export=applied "
        f"status={result.status} "
        f"generated_at={result.generated_at.isoformat()} "
        f"employees={result.employee_count} "
        f"output_path={result.output_path} "
        f"backup_path={result.backup_path or 'none'} "
        f"removed_backups={result.removed_backup_count}"
    )
    return 0


def _employee_consistency_payload(
    result: EmployeeConsistencyResult,
) -> dict[str, object]:
    return {
        "status": "ok" if result.is_consistent else "mismatch",
        "databaseEmployees": result.database_count,
        "csvEmployees": result.csv_count,
        "databaseOnlyEmployeeCodes": list(result.database_only_codes),
        "csvOnlyEmployeeCodes": list(result.csv_only_codes),
        "mismatchedEmployees": [
            {
                "employeeCode": difference.code,
                "fields": list(difference.fields),
            }
            for difference in result.field_differences
        ],
    }


def _employee_consistency_error_payload(exc: Exception) -> dict[str, object]:
    return {
        "status": "error",
        "databaseEmployees": None,
        "csvEmployees": None,
        "databaseOnlyEmployeeCodes": [],
        "csvOnlyEmployeeCodes": [],
        "mismatchedEmployees": [],
        "error": str(exc),
    }


def _check_employee_consistency(
    db: Database, employee_csv: Path, *, json_output: bool = False
) -> int:
    try:
        result = check_employee_data_consistency(db, employee_csv)
    except (EmployeeDataError, FileNotFoundError, RuntimeError, ValueError) as exc:
        if json_output:
            print(json.dumps(_employee_consistency_error_payload(exc), ensure_ascii=False))
            return 1
        raise

    if json_output:
        print(json.dumps(_employee_consistency_payload(result), ensure_ascii=False))
        return 0 if result.is_consistent else 1

    mismatch_count = (
        len(result.database_only_codes) + len(result.csv_only_codes) + len(result.field_differences)
    )
    print(
        "employee_data_consistency="
        f"{'ok' if result.is_consistent else 'mismatch'} "
        f"database_employees={result.database_count} csv_employees={result.csv_count}"
    )
    print(f"employee_count.database_enabled={result.database_count}")
    print(f"employee_count.csv_records={result.csv_count}")
    print(
        "employee_consistency="
        f"{'ok' if result.is_consistent else 'mismatch'} mismatches={mismatch_count}"
    )
    for code in result.database_only_codes:
        print(f"database_only employee_code={code}")
    for code in result.csv_only_codes:
        print(f"csv_only employee_code={code}")
    for difference in result.field_differences:
        print(
            f"field_mismatch employee_code={difference.code} fields={','.join(difference.fields)}"
        )
    return 0 if result.is_consistent else 1


def _record_employee_consistency(db: Database, employee_csv: Path, history_path: Path) -> int:
    recorded_at = datetime.now().astimezone().isoformat()
    try:
        result = check_employee_data_consistency(db, employee_csv)
    except (EmployeeDataError, FileNotFoundError, RuntimeError, ValueError) as exc:
        payload = _employee_consistency_error_payload(exc)
        exit_code = 1
    else:
        payload = _employee_consistency_payload(result)
        exit_code = 0 if result.is_consistent else 1

    history_path.parent.mkdir(parents=True, exist_ok=True)
    record = {"recordedAt": recorded_at, **payload}
    with history_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False))
        handle.write("\n")

    print(f"employee_data_consistency_recorded status={payload['status']} path={history_path}")
    return exit_code


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "backups":
            return _run_backups_command(args)

        if args.command == "database":
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s %(levelname)s %(name)s %(message)s",
            )
            return _run_database_command(args)

        config = load_config(args.root)
        logging.basicConfig(
            level=getattr(logging, config.log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        db = Database(config.database_path)
        if args.command == "run":
            return run(config, args.mode, args.dry_run, source=args.source)
        if args.command == "employees" and args.action == "import-csv":
            return _import_employees(db, config.employee_csv, args.apply)
        if args.command == "employees" and args.action == "export-csv":
            return _export_employees(db, config.employee_csv, args.apply)
        if args.command == "employees" and args.action == "check-consistency":
            return _check_employee_consistency(
                db, config.employee_csv, json_output=args.json_output
            )
        if args.command == "employees" and args.action == "record-consistency":
            return _record_employee_consistency(
                db,
                config.employee_csv,
                args.root / "data" / "employee-consistency-history.jsonl",
            )
        if args.command == "validate-config":
            employees = load_employees(config.employee_csv)
            print(f"configuration=ok employees={len(employees)}")
            print(f"employee_count.csv_records={len(employees)}")
            return 0
        if args.command == "health":
            db.initialize()
            print(f"database_integrity={db.integrity_check()}")
            print(f"employee_csv_exists={config.employee_csv.exists()}")
            return 0 if config.employee_csv.exists() and db.integrity_check() == "ok" else 1
        return 2
    except (
        ConfigError,
        EmployeeDataError,
        FileNotFoundError,
        KeyError,
        RuntimeError,
        ValueError,
    ) as exc:
        logging.error("Configuration error: %s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
