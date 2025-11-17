from __future__ import annotations

import csv
import os
import sqlite3
import sys
from pathlib import Path
from typing import Iterable, Tuple


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trading_calendar (
            market TEXT NOT NULL,
            day TEXT NOT NULL,
            is_trading_day INTEGER NOT NULL CHECK(is_trading_day IN (0,1)),
            PRIMARY KEY (market, day)
        )
        """
    )


def _upsert_rows(conn: sqlite3.Connection, rows: Iterable[Tuple[str, str, int]]) -> int:
    cur = conn.executemany(
        """
        INSERT INTO trading_calendar(market, day, is_trading_day)
        VALUES (?, ?, ?)
        ON CONFLICT(market, day) DO UPDATE SET is_trading_day=excluded.is_trading_day
        """,
        list(rows),
    )
    return cur.rowcount or 0


def main() -> int:
    """
    从 CSV 导入交易日历到 SQLite。

    使用：
        DB_PATH=data/portfolio.db python scripts/import_trading_calendar.py data/trading_calendar/a_shares.csv

    CSV 支持两种格式：
        1) market,day,is_trading_day
        2) day,is_trading_day （此时 market 默认为 "A"）
    """
    if len(sys.argv) < 2:
        print("用法：python scripts/import_trading_calendar.py <csv_path>")
        return 2
    db_path = os.getenv("DB_PATH", "data/portfolio.db")
    csv_path = Path(sys.argv[1])
    if not csv_path.exists():
        print(f"CSV 文件不存在：{csv_path}")
        return 2

    conn = sqlite3.connect(db_path)
    try:
        _ensure_table(conn)
        with conn, csv_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows: list[Tuple[str, str, int]] = []
            if {"market", "day", "is_trading_day"}.issubset(reader.fieldnames or {}):
                for r in reader:
                    rows.append((r["market"], r["day"], int(r["is_trading_day"])) )
            elif {"day", "is_trading_day"}.issubset(reader.fieldnames or {}):
                for r in reader:
                    rows.append(("A", r["day"], int(r["is_trading_day"])) )
            else:
                print("CSV 表头必须包含 day,is_trading_day（可选 market）")
                return 2

            affected = _upsert_rows(conn, rows)
            print(f"导入完成：{affected} 行")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())

