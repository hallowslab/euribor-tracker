from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS euribor_fixings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenor TEXT NOT NULL,
    fixing_date TEXT NOT NULL,
    rate REAL NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    UNIQUE (tenor, fixing_date)
);

CREATE INDEX IF NOT EXISTS idx_fixings_tenor_date ON euribor_fixings (tenor, fixing_date);

CREATE TABLE IF NOT EXISTS euribor_anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenor TEXT NOT NULL,
    fixing_date TEXT NOT NULL,
    old_rate REAL NOT NULL,
    new_rate REAL NOT NULL,
    detected_at TEXT NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mortgage_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    tenor TEXT NOT NULL,
    params TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_triggered_at TEXT,
    triggered_count INTEGER NOT NULL DEFAULT 0
);
"""


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def meta_get(self, key: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def meta_set(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO app_meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
