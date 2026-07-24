from __future__ import annotations

from division_overtime.kot_employee_sync import KotEmployee


class DevelopmentKotEmployeeSource:
    """Return deterministic KOT employees for local UI development."""

    def fetch(self) -> list[KotEmployee]:
        return [
            KotEmployee(
                code="90001",
                key="dev-kot-90001",
                last_name="山田",
                first_name="太郎",
                email="taro.yamada@example.invalid",
                division_code="156",
                division_name="営業第一部",
                group_codes=(),
                group_names=(),
                resignation_date="",
            ),
            KotEmployee(
                code="90002",
                key="dev-kot-90002-updated",
                last_name="佐藤",
                first_name="花子",
                email="hanako.updated@example.invalid",
                division_code="158",
                division_name="開発本部",
                group_codes=(),
                group_names=(),
                resignation_date="",
            ),
            KotEmployee(
                code="90004",
                key="dev-kot-90004",
                last_name="無効",
                first_name="社員",
                email="disabled@example.invalid",
                division_code="158",
                division_name="開発部",
                group_codes=(),
                group_names=(),
                resignation_date="",
            ),
            KotEmployee(
                code="90005",
                key="dev-kot-90005",
                last_name="新規",
                first_name="社員",
                email="new.employee@example.invalid",
                division_code="156",
                division_name="営業第一部",
                group_codes=("leave",),
                group_names=("休職表示確認",),
                resignation_date="",
            ),
        ]
