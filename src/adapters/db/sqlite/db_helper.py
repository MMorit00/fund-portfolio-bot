from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from src.app.config import enable_sql_debug, get_db_path

SCHEMA_VERSION = 1

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS funds (
    fund_code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    market TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_code TEXT NOT NULL,
    type TEXT NOT NULL,
    amount TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    status TEXT NOT NULL,
    market TEXT NOT NULL,
    shares TEXT,
    nav TEXT,
    remark TEXT,
    confirm_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS navs (
    fund_code TEXT NOT NULL,
    day TEXT NOT NULL,
    nav TEXT NOT NULL,
    PRIMARY KEY (fund_code, day)
);

CREATE TABLE IF NOT EXISTS dca_plans (
    fund_code TEXT PRIMARY KEY,
    amount TEXT NOT NULL,
    frequency TEXT NOT NULL,
    rule TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alloc_config (
    asset_class TEXT PRIMARY KEY,
    target_weight TEXT NOT NULL,
    max_deviation TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class SqliteDbHelper:
    """SQLite 连接/Schema 初始化 Helper。"""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = Path(db_path or get_db_path())
        self._conn: Optional[sqlite3.Connection] = None

    def get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            if self.db_path.parent:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            if enable_sql_debug():
                conn.set_trace_callback(print)
            self._conn = conn
        return self._conn

    def init_schema_if_needed(self) -> None:
        conn = self.get_connection()
        with conn:
            conn.executescript(SCHEMA_DDL)
            row = conn.execute(
                "SELECT value FROM meta WHERE key = ?",
                ("schema_version",),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES (?, ?)",
                    ("schema_version", str(SCHEMA_VERSION)),
                )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
