from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from src.core.config import enable_sql_debug, get_db_path

SCHEMA_VERSION = 16

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS funds (
    fund_code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    market TEXT NOT NULL,
    alias TEXT
);

CREATE TABLE IF NOT EXISTS fund_fee_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_code TEXT NOT NULL,
    fee_type TEXT NOT NULL,
    charge_basis TEXT NOT NULL,
    rate TEXT NOT NULL,
    min_hold_days INTEGER,
    max_hold_days INTEGER,
    FOREIGN KEY (fund_code) REFERENCES funds(fund_code) ON DELETE CASCADE,
    UNIQUE (fund_code, fee_type, min_hold_days)
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
    remark TEXT,
    pricing_date TEXT NOT NULL,
    confirm_date TEXT NOT NULL,
    confirmation_status TEXT DEFAULT 'normal',
    delayed_reason TEXT,
    delayed_since TEXT,
    external_id TEXT UNIQUE,
    import_batch_id INTEGER,
    dca_plan_key TEXT,
    fee TEXT,
    apply_amount TEXT,
    apply_shares TEXT
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
    rule TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
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

CREATE TABLE IF NOT EXISTS action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    source TEXT NOT NULL,
    acted_at TEXT NOT NULL,
    fund_code TEXT,
    target_date TEXT,
    trade_id INTEGER,
    intent TEXT,
    note TEXT,
    strategy TEXT
);

CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS fund_restrictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_code TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,
    restriction_type TEXT NOT NULL,
    limit_amount TEXT,
    source TEXT NOT NULL,
    source_url TEXT,
    note TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (fund_code) REFERENCES funds(fund_code)
);

CREATE INDEX IF NOT EXISTS idx_fund_restrictions_fund_date
ON fund_restrictions(fund_code, start_date, end_date);
"""


class DbHelper:
    """
    SQLite 连接/Schema 初始化 Helper。

    职责：
    - 初始化数据库文件与表结构（如不存在则创建）；
    - 提供带 RowFactory 的连接；
    - 维护一个进程内共享连接（简单场景）。
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = Path(db_path or get_db_path())
        self._conn: Optional[sqlite3.Connection] = None

    def get_connection(self) -> sqlite3.Connection:
        """
        获取（或创建）SQLite 连接。

        Returns:
            已初始化的 sqlite3.Connection，`row_factory` 已设置为 sqlite3.Row。
        """
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
        """
        初始化表结构与 meta.schema_version（若未设置）。

        副作用：可能创建目录/文件，执行 DDL。
        """
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
            else:
                # 开发阶段：版本不匹配时提示重建数据库
                current_version = int(row["value"])
                if current_version < SCHEMA_VERSION:
                    raise RuntimeError(
                        f"[DbHelper] Schema 版本过旧（当前 v{current_version}，需要 v{SCHEMA_VERSION}）。"
                        f"开发阶段请删除 {self.db_path} 后重新运行。"
                    )

    def close(self) -> None:
        """关闭连接并释放引用。"""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
