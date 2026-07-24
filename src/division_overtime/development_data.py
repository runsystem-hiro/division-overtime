from __future__ import annotations

from division_overtime.employee_management import EmployeeChange


def development_employees() -> list[EmployeeChange]:
    return [
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
