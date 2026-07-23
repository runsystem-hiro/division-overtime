from division_overtime.employee_consistency import compare_employee_data
from division_overtime.models import Employee


def _employee(code: str, **overrides) -> Employee:
    values = {
        "code": code,
        "employee_key": "key",
        "last_name": "田中",
        "first_name": "太郎",
        "email": "t@example.com",
        "division_code": "300",
        "division_name": "営業部",
        "personal_target_minutes": 1200,
    }
    values.update(overrides)
    return Employee(**values)


def test_compare_employee_data_matches_independent_of_order():
    result = compare_employee_data(
        [_employee("00002"), _employee("00001")],
        [_employee("00001"), _employee("00002")],
    )

    assert result.is_consistent is True
    assert result.database_count == 2
    assert result.csv_count == 2


def test_compare_employee_data_reports_all_difference_types():
    result = compare_employee_data(
        [_employee("00001"), _employee("00002")],
        [
            _employee("00001", employee_key="changed", personal_target_minutes=None),
            _employee("00003"),
        ],
    )

    assert result.is_consistent is False
    assert result.database_only_codes == ("00002",)
    assert result.csv_only_codes == ("00003",)
    assert len(result.field_differences) == 1
    difference = result.field_differences[0]
    assert difference.code == "00001"
    assert difference.fields == ("kot_key", "personal_target_minutes")
