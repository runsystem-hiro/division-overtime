from division_overtime.database import Database


def test_database_initialization(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.initialize()
    assert db.integrity_check() == "ok"
