from __future__ import annotations

import sqlite3
from datetime import date


class SqliteCalendarStore:
    """
    SQLite 日历存取实现（基于 trading_calendar 表）。

    约定：
    - 表结构：trading_calendar(market TEXT, day TEXT, is_trading_day INTEGER)
      （兼容现有表结构，market 列作为 calendar_key 使用）

    缺口处理：
    - 严格模式：若缺失记录则直接抛错，杜绝工作日近似导致的误判。
    - 通过"注油/修补"任务维护完整日历数据。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def is_open(self, calendar_key: str, day: date) -> bool:
        """检查指定日期是否为交易日。"""
        row = self.conn.execute(
            "SELECT is_trading_day FROM trading_calendar WHERE market = ? AND day = ?",
            (calendar_key, day.isoformat()),
        ).fetchone()
        if row is None:
            raise RuntimeError(
                f"trading_calendar 缺失记录：calendar_key={calendar_key} day={day.isoformat()}"
            )
        return int(row[0]) == 1
