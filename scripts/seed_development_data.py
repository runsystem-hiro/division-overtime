from __future__ import annotations

import argparse
import os
import shutil
from datetime import datetime
from pathlib import Path

from division_overtime.config import ConfigError, _load_toml_config
from division_overtime.database import Database
from division_overtime.development_data import development_employees
from division_overtime.employee_management import EmployeeManagementService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reset the local development employee data.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return parser


def main() -> int:
    args = _parser().parse_args()
    root = args.root.resolve()
    os.environ["DIVISION_OVERTIME_ENV"] = "development"
    try:
        raw = _load_toml_config(root)
        app = raw["app"]
        database_path = root / str(app["database_path"])
        employee_csv = root / str(app["employee_csv"])
    except (ConfigError, KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"invalid development configuration: {exc}") from exc

    shutil.rmtree(database_path.parent, ignore_errors=True)
    employee_csv.unlink(missing_ok=True)

    database = Database(database_path)
    database.initialize()
    service = EmployeeManagementService(database, employee_csv)
    now = datetime.now().astimezone()
    employees = development_employees()
    for employee in employees:
        service.create_employee(employee, now)

    print(f"development_database={database_path}")
    print(f"development_employee_csv={employee_csv}")
    print(f"employees={len(employees)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
