from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from src.core.rules.precision import quantize_nav


class NavRepo:
    """
    净值仓储（SQLite）。

    职责：按 (fund_code, day) 写入/读取官方单位净值，采用字符串持久化 Decimal。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert(self, fund_code: str, day: date, nav: Decimal) -> None:
        """插入或更新某日净值（主键冲突时覆盖）。"""
        normalized_nav = quantize_nav(nav)
        with self.conn:
            self.conn.execute(
                (
                    "INSERT INTO navs(fund_code, day, nav) VALUES(?, ?, ?) "
                    "ON CONFLICT(fund_code, day) DO UPDATE SET nav=excluded.nav"
                ),
                (fund_code, day.isoformat(), format(normalized_nav, "f")),
            )

    def get(self, fund_code: str, day: date) -> Decimal | None:
        """读取某日净值，未找到返回 None。"""
        row = self.conn.execute(
            "SELECT nav FROM navs WHERE fund_code = ? AND day = ?",
            (fund_code, day.isoformat()),
        ).fetchone()
        if not row:
            return None
        return Decimal(row["nav"])

    def exists(self, fund_code: str, day: date) -> bool:
        """
        检查某日净值是否存在（v0.3.2 新增）。

        Args:
            fund_code: 基金代码。
            day: 日期。

        Returns:
            存在返回 True，否则返回 False。
        """
        row = self.conn.execute(
            "SELECT 1 FROM navs WHERE fund_code = ? AND day = ?",
            (fund_code, day.isoformat()),
        ).fetchone()
        return row is not None
