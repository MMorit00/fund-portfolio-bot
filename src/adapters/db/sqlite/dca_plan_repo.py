from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal
from typing import List, Optional

from src.core.dca_plan import DcaPlan
from src.usecases.ports import DcaPlanRepo


class SqliteDcaPlanRepo(DcaPlanRepo):
    """定投计划仓储。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def list_due_plans(self, day: date) -> List[DcaPlan]:  # type: ignore[override]
        # TODO-MVP: 当前实现返回所有定投计划，
        # 实际的 “是否到期” 判断在 RunDailyDca._due 中完成。
        rows = self.conn.execute("SELECT * FROM dca_plans ORDER BY fund_code").fetchall()
        return [_row_to_plan(r) for r in rows]

    def get_plan(self, fund_code: str) -> Optional[DcaPlan]:  # type: ignore[override]
        row = self.conn.execute(
            "SELECT * FROM dca_plans WHERE fund_code = ?",
            (fund_code,),
        ).fetchone()
        if not row:
            return None
        return _row_to_plan(row)


def _row_to_plan(row: sqlite3.Row) -> DcaPlan:
    """将 SQLite Row 转换为 DcaPlan 对象。"""
    return DcaPlan(
        fund_code=row["fund_code"],
        amount=Decimal(row["amount"]),
        frequency=row["frequency"],
        rule=row["rule"],
    )

