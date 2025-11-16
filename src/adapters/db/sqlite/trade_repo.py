from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from src.core.trade import Trade
from src.core.trading.settlement import get_confirm_date
from src.core.trading.calendar import TradingCalendar
from src.usecases.ports import TradeRepo


class SqliteTradeRepo(TradeRepo):
    """SQLite 交易仓储实现。"""

    def __init__(self, conn: sqlite3.Connection, calendar: TradingCalendar) -> None:
        """
        Args:
            conn: SQLite数据库连接
            calendar: 交易日历实例

        Returns:
            None
        """
        self.conn = conn
        self.calendar = calendar

    def add(self, trade: Trade) -> Trade:  # type: ignore[override]
        """
        Args:
            trade: 待新增的交易对象（id可为None）

        Returns:
            Trade: 包含数据库生成id的完整交易对象
        """
        confirm_day = get_confirm_date(trade.market, trade.trade_date, self.calendar)
        with self.conn:
            cursor = self.conn.execute(
                (
                    "INSERT INTO trades (fund_code, type, amount, trade_date, status, market, shares, nav, remark, confirm_date) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                (
                    trade.fund_code,
                    trade.type,
                    format(trade.amount, "f"),
                    trade.trade_date.isoformat(),
                    trade.status,
                    trade.market,
                    _decimal_to_str(trade.shares),
                    None,
                    trade.remark,
                    confirm_day.isoformat(),
                ),
            )
            trade_id = cursor.lastrowid or 0
        return Trade(
            id=int(trade_id),
            fund_code=trade.fund_code,
            type=trade.type,
            amount=trade.amount,
            trade_date=trade.trade_date,
            status=trade.status,
            market=trade.market,
            shares=trade.shares,
            remark=trade.remark,
        )

    def list_pending_to_confirm(self, confirm_date: date) -> List[Trade]:  # type: ignore[override]
        """
        Args:
            confirm_date: 确认日期，查询该日期需要确认的交易

        Returns:
            List[Trade]: 待确认交易列表，按交易id升序排序
        """
        rows = self.conn.execute(
            "SELECT * FROM trades WHERE status = ? AND confirm_date = ? ORDER BY id",
            ("pending", confirm_date.isoformat()),
        ).fetchall()
        return [_row_to_trade(r) for r in rows]

    def confirm(self, trade_id: int, shares: Decimal, nav: Decimal) -> None:  # type: ignore[override]
        """
        Args:
            trade_id: 交易记录的数据库id
            shares: 确认的份额数量
            nav: 确认时使用的净值

        Returns:
            None
        """
        with self.conn:
            self.conn.execute(
                "UPDATE trades SET status = ?, shares = ?, nav = ? WHERE id = ?",
                (
                    "confirmed",
                    _decimal_to_str(shares),
                    format(nav, "f"),
                    trade_id,
                ),
            )

    def position_shares(self) -> Dict[str, Decimal]:  # type: ignore[override]
        """
        Args:
            None

        Returns:
            Dict[str, Decimal]: 基金代码到净持仓份额的映射（买入为正，卖出为负）
        """
        rows = self.conn.execute(
            "SELECT fund_code, type, shares FROM trades WHERE status = 'confirmed' AND shares IS NOT NULL"
        ).fetchall()
        position: Dict[str, Decimal] = {}
        for row in rows:
            shares = Decimal(row["shares"])
            if row["type"] == "sell":
                shares = -shares
            position[row["fund_code"]] = position.get(row["fund_code"], Decimal("0")) + shares
        return position

    def skip_dca_for_date(self, fund_code: str, day: date) -> int:  # type: ignore[override]
        """
        Args:
            fund_code: 基金代码
            day: 需要跳过的日期

        Returns:
            int: 更新的交易记录数量（影响行数）
        """
        cur = self.conn.execute(
            """
            UPDATE trades
            SET status = 'skipped'
            WHERE fund_code = ?
              AND type = 'buy'
              AND status = 'pending'
              AND trade_date = ?
            """,
            (fund_code, day.isoformat()),
        )
        self.conn.commit()
        return cur.rowcount


def _decimal_to_str(value: Optional[Decimal]) -> Optional[str]:
    """
    Args:
        value: Decimal对象，可能为None

    Returns:
        Optional[str]: 格式化的字符串，None输入返回None
    """
    if value is None:
        return None
    return format(value, "f")


def _row_to_trade(row: sqlite3.Row) -> Trade:
    """
    Args:
        row: SQLite查询结果行，包含trades表的所有字段

    Returns:
        Trade: 转换后的Trade对象
    """
    shares = row["shares"]
    return Trade(
        id=int(row["id"]),
        fund_code=row["fund_code"],
        type=row["type"],
        amount=Decimal(row["amount"]),
        trade_date=date.fromisoformat(row["trade_date"]),
        status=row["status"],
        market=row["market"],
        shares=Decimal(shares) if shares is not None else None,
        remark=row["remark"],
    )
