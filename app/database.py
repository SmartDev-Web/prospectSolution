"""SQLite storage layer shared by every service."""
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.config import DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS prospects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    legal_name TEXT,
    siret TEXT,
    naf_code TEXT,
    sector_key TEXT,
    category_label TEXT,
    company_category TEXT,
    address TEXT,
    postal_code TEXT,
    city TEXT,
    latitude REAL,
    longitude REAL,
    phone TEXT,
    email TEXT,
    website_url TEXT,
    website_domain TEXT,
    website_origin TEXT,
    social_url TEXT,
    creation_date TEXT,
    employee_range TEXT,
    google_rating REAL,
    google_review_count INTEGER,
    google_maps_url TEXT,
    google_place_key TEXT,
    sources TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'new',
    notes TEXT NOT NULL DEFAULT '',
    next_follow_up TEXT,
    score INTEGER,
    opportunity_level TEXT,
    website_check_done INTEGER NOT NULL DEFAULT 0,
    last_scan_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS index_prospects_siret ON prospects (siret);
CREATE INDEX IF NOT EXISTS index_prospects_domain ON prospects (website_domain);
CREATE INDEX IF NOT EXISTS index_prospects_place ON prospects (google_place_key);
CREATE INDEX IF NOT EXISTS index_prospects_postal_code ON prospects (postal_code);
CREATE INDEX IF NOT EXISTS index_prospects_coordinates ON prospects (latitude, longitude);
CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL REFERENCES prospects (id) ON DELETE CASCADE,
    scanned_at TEXT NOT NULL,
    final_url TEXT,
    http_status INTEGER,
    reachable INTEGER NOT NULL,
    score INTEGER,
    metrics TEXT NOT NULL,
    findings TEXT NOT NULL,
    contacts TEXT NOT NULL,
    desktop_screenshot TEXT,
    mobile_screenshot TEXT,
    report TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS index_scans_prospect ON scans (prospect_id, scanned_at);
CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL REFERENCES prospects (id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    outcome TEXT,
    content TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS index_activities_prospect ON activities (prospect_id, created_at);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""
JSON_COLUMNS = {"sources", "metrics", "findings", "contacts", "report"}


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def decode_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """Convert a SQLite row into a dictionary, decoding JSON columns."""
    if row is None:
        return None
    decoded_row = dict(row)
    for column_name in JSON_COLUMNS.intersection(decoded_row):
        raw_value = decoded_row[column_name]
        decoded_row[column_name] = json.loads(raw_value) if raw_value else None
    return decoded_row


class Database:
    """Thread-safe wrapper around a single SQLite connection."""

    def __init__(self, database_path: Path) -> None:
        self._connection = sqlite3.connect(database_path, check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.executescript(SCHEMA)

    def execute(self, sql: str, parameters: tuple | dict = ()) -> sqlite3.Cursor:
        """Run a statement and return its cursor."""
        with self._lock:
            return self._connection.execute(sql, parameters)

    def fetch_one(self, sql: str, parameters: tuple | dict = ()) -> dict[str, Any] | None:
        """Run a query and return the first decoded row."""
        with self._lock:
            return decode_row(self._connection.execute(sql, parameters).fetchone())

    def fetch_all(self, sql: str, parameters: tuple | dict = ()) -> list[dict[str, Any]]:
        """Run a query and return every decoded row."""
        with self._lock:
            return [decode_row(row) for row in self._connection.execute(sql, parameters).fetchall()]

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Group several statements into one atomic transaction."""
        with self._lock:
            self._connection.execute("BEGIN")
            try:
                yield self._connection
                self._connection.execute("COMMIT")
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise

    def close(self) -> None:
        """Close the underlying connection."""
        with self._lock:
            self._connection.close()


_database_instance: Database | None = None


def get_database() -> Database:
    """Return the shared database, opening it on first use."""
    global _database_instance
    if _database_instance is None:
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _database_instance = Database(DATABASE_PATH)
    return _database_instance


def use_database(database: Database) -> None:
    """Replace the shared database instance, used by tests."""
    global _database_instance
    _database_instance = database
