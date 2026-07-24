from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

from .config import ConfigError, load_config
from .database import Database
from .employee_consistency import (
    EmployeeConsistencyResult,
    check_employee_data_consistency,
)
from .employee_repository import EmployeeRepository
from .employees import EmployeeDataError, generate_employee_csv, load_employees
from .service import run


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="division-overtime")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("mode", choices=["threshold", "weekly"])
    run_parser.add_argument("--dry-run", action="store_true")
    sub.add_parser("health")
    db_parser = sub.add_parser("database")
    db_parser.add_argument("action", choices=["init", "status"])
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
        f"backup_path={result.backup_path or 'none'}"
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

    print(
        "employee_data_consistency="
        f"{'ok' if result.is_consistent else 'mismatch'} "
        f"database_employees={result.database_count} csv_employees={result.csv_count}"
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
        config = load_config(args.root)
        logging.basicConfig(
            level=getattr(logging, config.log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        db = Database(config.database_path)
        if args.command == "run":
            return run(config, args.mode, args.dry_run)
        if args.command == "database":
            db.initialize()
            if args.action == "status":
                print(f"database={db.path}")
                print(f"integrity_check={db.integrity_check()}")
            return 0
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
