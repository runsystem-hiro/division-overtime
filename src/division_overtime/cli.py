from __future__ import annotations

import argparse
import logging
import tempfile
from datetime import datetime
from pathlib import Path

from .config import ConfigError, load_config
from .database import Database
from .employee_repository import EmployeeRepository
from .employees import EmployeeDataError, load_employees, write_employees
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
    employees_parser.add_argument("action", choices=["import-csv", "export-csv"])
    employees_parser.add_argument("--apply", action="store_true")
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

    employee_csv.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{employee_csv.name}.",
            suffix=".tmp",
            dir=employee_csv.parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
        write_employees(temp_path, employees)
        validated = load_employees(temp_path)
        if len(validated) != len(employees):
            raise EmployeeDataError("Generated employee CSV validation count mismatch")
        temp_path.replace(employee_csv)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    print(f"employee_csv_export=applied employees={len(employees)}")
    return 0


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
