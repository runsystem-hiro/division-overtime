from __future__ import annotations

import logging

from division_overtime.employee_shadow import compare_employee_lists, log_employee_shadow_read
from division_overtime.models import Employee


def employee(code: str, key: str = "secret-key") -> Employee:
    return Employee(code, key, "田中", "太郎", "tanaka@example.com", "300", "営業部", 600)


def test_compare_employee_lists_identifies_each_difference_type():
    diff = compare_employee_lists(
        [employee("00001"), employee("00002"), employee("00003", "csv-key")],
        [employee("00002"), employee("00003", "sqlite-key"), employee("00004")],
    )

    assert diff.csv_only_codes == ("00001",)
    assert diff.sqlite_only_codes == ("00004",)
    assert diff.changed_codes == ("00003",)
    assert not diff.matches


def test_shadow_read_logs_matching_counts(caplog):
    class MatchingSource:
        def list_employees(self):
            return [employee("00001")]

    with caplog.at_level(logging.INFO, logger="division_overtime.employee_shadow"):
        log_employee_shadow_read([employee("00001")], MatchingSource())

    assert "employee_shadow_read=ok csv_employees=1 sqlite_employees=1" in caplog.text


def test_shadow_read_logs_codes_without_sensitive_values(caplog):
    class DifferentSource:
        def list_employees(self):
            return [employee("00002", "sqlite-secret")]

    with caplog.at_level(logging.WARNING, logger="division_overtime.employee_shadow"):
        log_employee_shadow_read([employee("00001", "csv-secret")], DifferentSource())

    assert "csv_only=00001" in caplog.text
    assert "sqlite_only=00002" in caplog.text
    assert "csv-secret" not in caplog.text
    assert "sqlite-secret" not in caplog.text
    assert "tanaka@example.com" not in caplog.text


def test_shadow_read_failure_is_logged_without_raising(caplog):
    class FailingSource:
        def list_employees(self):
            raise RuntimeError("secret-key must not be logged")

    with caplog.at_level(logging.WARNING, logger="division_overtime.employee_shadow"):
        log_employee_shadow_read([employee("00001")], FailingSource())

    assert "employee_shadow_read=failed error_type=RuntimeError" in caplog.text
    assert "secret-key must not be logged" not in caplog.text
