"""Shared fixtures: every test runs against a fresh temporary database."""
import pytest

from app.database import Database, use_database


@pytest.fixture(autouse=True)
def temporary_database(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    use_database(database)
    yield database
    database.close()
