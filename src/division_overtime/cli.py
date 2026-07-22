from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .config import ConfigError, load_config
from .database import Database
from .employees import EmployeeDataError, load_employees
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
    sub.add_parser("validate-config")
    return parser


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
    except (ConfigError, EmployeeDataError, FileNotFoundError, KeyError, ValueError) as exc:
        logging.error("Configuration error: %s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
