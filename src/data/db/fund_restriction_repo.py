"""基金限购/暂停公告 Repo（v0.4.4）。"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal

from src.core.models.fund_restriction import FundRestrictionFact


class FundRestrictionRepo:
    """
    基金限购/暂停公告仓储（SQLite）。

    职责：
    - 添加、更新限制记录
    - 查询某日有效的限制（用于 DCA 分析）
    - 查询时间段内的限制记录
    - 结束最新 active 限制
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(self, fact: FundRestrictionFact) -> int:
        """
        添加限制记录。

        Args:
            fact: FundRestrictionFact 对象。

        Returns:
            新插入记录的 ID。

        副作用：
            插入 fund_restrictions 表，自动提交。
        """
        cursor = self.conn.execute(
            """
            INSERT INTO fund_restrictions (
                fund_code, start_date, end_date, restriction_type,
                limit_amount, source, source_url, note, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fact.fund_code,
                fact.start_date.isoformat(),
                fact.end_date.isoformat() if fact.end_date else None,
                fact.restriction_type,
                str(fact.limit_amount) if fact.limit_amount is not None else None,
                fact.source,
                fact.source_url,
                fact.note,
                datetime.now().isoformat(),
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def update_end_date(self, id: int, end_date: date) -> None:
        """
        更新限制记录的结束日期。

        Args:
            id: 限制记录 ID。
            end_date: 新的结束日期。

        副作用：
            更新 fund_restrictions 表的 end_date 字段，自动提交。
        """
        self.conn.execute(
            "UPDATE fund_restrictions SET end_date = ? WHERE id = ?",
            (end_date.isoformat(), id),
        )
        self.conn.commit()

    def list_active_on(self, fund_code: str, check_date: date) -> list[FundRestrictionFact]:
        """
        查询某只基金在指定日期有效的限制记录。

        Args:
            fund_code: 基金代码。
            check_date: 检查日期。

        Returns:
            FundRestrictionFact 列表（在该日期有效的限制）。

        逻辑：
            start_date <= check_date AND (end_date IS NULL OR end_date >= check_date)
        """
        rows = self.conn.execute(
            """
            SELECT * FROM fund_restrictions
            WHERE fund_code = ?
              AND start_date <= ?
              AND (end_date IS NULL OR end_date >= ?)
            ORDER BY start_date DESC
            """,
            (fund_code, check_date.isoformat(), check_date.isoformat()),
        ).fetchall()
        return [_row_to_fact(r) for r in rows]

    def list_by_period(
        self,
        fund_code: str,
        start_date: date,
        end_date: date,
    ) -> list[FundRestrictionFact]:
        """
        查询某只基金在指定时间段内的所有限制记录（包括部分重叠）。

        Args:
            fund_code: 基金代码。
            start_date: 查询起始日期。
            end_date: 查询结束日期。

        Returns:
            FundRestrictionFact 列表。

        逻辑：
            限制记录与查询时间段有重叠：
            - 限制开始日期 <= 查询结束日期
            - 限制结束日期 >= 查询开始日期 OR 限制仍在生效（end_date IS NULL）
        """
        rows = self.conn.execute(
            """
            SELECT * FROM fund_restrictions
            WHERE fund_code = ?
              AND start_date <= ?
              AND (end_date IS NULL OR end_date >= ?)
            ORDER BY start_date DESC
            """,
            (fund_code, end_date.isoformat(), start_date.isoformat()),
        ).fetchall()
        return [_row_to_fact(r) for r in rows]

    def end_latest_active(self, fund_code: str, restriction_type: str, end_date: date) -> bool:
        """
        结束指定基金和类型的最新 active 限制记录。

        Args:
            fund_code: 基金代码。
            restriction_type: 限制类型。
            end_date: 结束日期。

        Returns:
            是否成功结束（True=找到并更新，False=未找到匹配记录）。

        副作用：
            更新符合条件的最新记录的 end_date，自动提交。
        """
        cursor = self.conn.execute(
            """
            UPDATE fund_restrictions
            SET end_date = ?
            WHERE id = (
                SELECT id FROM fund_restrictions
                WHERE fund_code = ? AND restriction_type = ? AND end_date IS NULL
                ORDER BY start_date DESC
                LIMIT 1
            )
            """,
            (end_date.isoformat(), fund_code, restriction_type),
        )
        self.conn.commit()
        return cursor.rowcount > 0


def _row_to_fact(row: sqlite3.Row) -> FundRestrictionFact:
    """
    将数据库行转换为 FundRestrictionFact 对象。

    Args:
        row: sqlite3.Row 对象。

    Returns:
        FundRestrictionFact 对象。
    """
    return FundRestrictionFact(
        fund_code=row["fund_code"],
        start_date=date.fromisoformat(row["start_date"]),
        end_date=date.fromisoformat(row["end_date"]) if row["end_date"] else None,
        restriction_type=row["restriction_type"],
        limit_amount=Decimal(row["limit_amount"]) if row["limit_amount"] else None,
        source=row["source"],
        source_url=row["source_url"],
        note=row["note"],
    )
