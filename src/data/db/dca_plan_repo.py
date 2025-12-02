from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from src.core.models.dca_plan import DcaPlan
from src.core.rules.precision import quantize_amount


class DcaPlanRepo:
    """
    定投计划仓储（SQLite）。

    说明：当前实现 `list_due(day)` 返回全部计划，是否到期的判断在用例层完成。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def list_due(self, day: date) -> list[DcaPlan]:
        """返回需检查的定投计划（MVP 返回全部）。"""
        rows = self.conn.execute("SELECT * FROM dca_plans ORDER BY fund_code").fetchall()
        return [_row_to_plan(r) for r in rows]

    def get(self, fund_code: str) -> DcaPlan | None:
        """读取某基金定投计划，未配置返回 None。"""
        row = self.conn.execute(
            "SELECT * FROM dca_plans WHERE fund_code = ?",
            (fund_code,),
        ).fetchone()
        if not row:
            return None
        return _row_to_plan(row)

    def upsert(
        self,
        fund_code: str,
        amount: Decimal,
        frequency: str,
        rule: str,
        status: str = "active",
    ) -> None:
        """
        创建或更新定投计划（v0.3.2 新增）。

        Args:
            fund_code: 基金代码。
            amount: 定投金额。
            frequency: 频率（daily/weekly/monthly）。
            rule: 规则（对应频率的具体日期/星期）。
            status: 状态（active/disabled），默认 active。

        副作用：
            按 (fund_code) 幂等插入或更新 dca_plans 表。
        """
        normalized_amount = quantize_amount(amount)

        self.conn.execute(
            """
            INSERT INTO dca_plans (fund_code, amount, frequency, rule, status)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(fund_code) DO UPDATE SET
                amount = excluded.amount,
                frequency = excluded.frequency,
                rule = excluded.rule,
                status = excluded.status
            """,
            (fund_code, str(normalized_amount), frequency, rule, status),
        )
        self.conn.commit()

    def set_status(self, fund_code: str, status: str) -> None:
        """
        设置定投计划状态（v0.3.2 新增）。

        Args:
            fund_code: 基金代码。
            status: 状态（active/disabled）。

        副作用：
            更新 dca_plans 表的 status 字段。

        Raises:
            ValueError: 计划不存在时抛出。
        """
        cursor = self.conn.execute(
            "UPDATE dca_plans SET status = ? WHERE fund_code = ?",
            (status, fund_code),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"定投计划不存在：{fund_code}")
        self.conn.commit()

    def list_all(self) -> list[DcaPlan]:
        """
        查询所有定投计划（v0.3.2 新增）。

        Returns:
            所有定投计划列表（包括 active 和 disabled）。
        """
        rows = self.conn.execute("SELECT * FROM dca_plans ORDER BY fund_code").fetchall()
        return [_row_to_plan(r) for r in rows]

    def list_active(self) -> list[DcaPlan]:
        """
        查询活跃定投计划（v0.3.2 新增）。

        Returns:
            状态为 active 的定投计划列表。
        """
        rows = self.conn.execute(
            "SELECT * FROM dca_plans WHERE status = 'active' ORDER BY fund_code"
        ).fetchall()
        return [_row_to_plan(r) for r in rows]

    def delete(self, fund_code: str) -> None:
        """
        删除定投计划（v0.3.4 新增）。

        Args:
            fund_code: 基金代码。

        Raises:
            ValueError: 计划不存在时抛出。

        副作用：
            从 dca_plans 表删除指定计划。
        """
        cursor = self.conn.execute(
            "DELETE FROM dca_plans WHERE fund_code = ?",
            (fund_code,),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"定投计划不存在：{fund_code}")
        self.conn.commit()


def _row_to_plan(row: sqlite3.Row) -> DcaPlan:
    """将 SQLite Row 转换为 DcaPlan 对象。"""
    return DcaPlan(
        fund_code=row["fund_code"],
        amount=Decimal(row["amount"]),
        frequency=row["frequency"],
        rule=row["rule"],
        status=row["status"],
    )
