from __future__ import annotations

import argparse
import os
import shutil
from datetime import datetime
from pathlib import Path

from division_overtime.config import ConfigError, _load_toml_config
from division_overtime.database import Database
from division_overtime.employee_management import EmployeeChange, EmployeeManagementService


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

    employees = [
        EmployeeChange(
            "90001",
            "山田",
            "太郎",
            "taro.yamada@example.invalid",
            "156",
            "営業第一部",
            1800,
            True,
            "",
            "通常表示確認",
            "dev-kot-90001",
        ),
        EmployeeChange(
            "90002",
            "佐藤",
            "花子",
            "hanako.sato@example.invalid",
            "158",
            "開発部",
            None,
            True,
            "",
            "上限未設定確認",
            "dev-kot-90002",
        ),
        EmployeeChange(
            "90003",
            "表示確認用長姓",
            "表示確認用長名",
            "long-name@example.invalid",
            "156",
            "非常に長い部署名称の表示確認部門",
            1200,
            True,
            "",
            "長い文字列のレイアウト確認",
            "dev-kot-90003",
        ),
        EmployeeChange(
            "90004",
            "無効",
            "社員",
            "disabled@example.invalid",
            "158",
            "開発部",
            1200,
            False,
            "開発環境での再有効化確認",
            "無効社員の表示確認",
            "dev-kot-90004",
        ),
    ]
    for employee in employees:
        service.create_employee(employee, now)

    print(f"development_database={database_path}")
    print(f"development_employee_csv={employee_csv}")
    print(f"employees={len(employees)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
