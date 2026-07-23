from pathlib import Path

from division_overtime.employees import load_employees


def test_load_employee_csv(tmp_path: Path):
    path = tmp_path / "employee.csv"
    path.write_text(
        "社員番号,キー,氏,名,メールアドレス,部署コード,部署名,個人別残業上限分\n"
        "00001,key,田中,太郎,t@example.com,300,営業部,1200\n",
        encoding="utf-8",
    )
    employees = load_employees(path)
    assert employees[0].code == "00001"
    assert employees[0].personal_target_minutes == 1200


def test_csv_employee_source_matches_existing_loader(tmp_path: Path):
    from division_overtime.employee_source import CsvEmployeeSource

    path = tmp_path / "employee.csv"
    path.write_text(
        "社員番号,キー,氏,名,メールアドレス,部署コード,部署名,個人別残業上限分\n"
        "00002,key-2,佐藤,次郎,s@example.com,400,開発部,\n"
        "00001,key-1,田中,太郎,t@example.com,300,営業部,1200\n",
        encoding="utf-8",
    )

    assert CsvEmployeeSource(path).list_employees() == load_employees(path)
