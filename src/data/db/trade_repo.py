from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from src.core.models.trade import Trade
from src.core.rules.settlement import calc_settlement_dates, default_policy

if TYPE_CHECKING:
    from src.data.db.calendar import CalendarService


class TradeRepo:
    """
    SQLite 交易仓储实现。

    负责按当前确认规则在创建交易时预写 `confirm_date`，并提供：
    - 待确认交易查询；
    - 确认更新（写入份额与确认用 NAV）；
    - 已确认持仓份额聚合。
    """

    def __init__(self, conn: sqlite3.Connection, calendar: "CalendarService") -> None:
        self.conn = conn
        self.calendar = calendar

    def add(self, trade: Trade) -> Trade:  # type: ignore[override]
        """新增一条交易记录，并按策略写入定价日/确认日。"""
        policy = default_policy(trade.market)
        pricing_day, confirm_day = calc_settlement_dates(trade.trade_date, policy, self.calendar)
        with self.conn:
            cursor = self.conn.execute(
                (
                    "INSERT INTO trades (fund_code, type, amount, trade_date, status, market, "  # noqa: E501
                    "shares, nav, remark, pricing_date, confirm_date, confirmation_status, delayed_reason, delayed_since) "  # noqa: E501
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
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
                    pricing_day.isoformat(),
                    confirm_day.isoformat(),
                    trade.confirmation_status,
                    trade.delayed_reason,
                    trade.delayed_since.isoformat() if trade.delayed_since else None,
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
            pricing_date=pricing_day,
            confirm_date=confirm_day,
            confirmation_status=trade.confirmation_status,
            delayed_reason=trade.delayed_reason,
            delayed_since=trade.delayed_since,
        )

    def list_pending_to_confirm(self, confirm_date: date) -> list[Trade]:  # type: ignore[override]
        """
        查询待确认交易（v0.2.1：包括过期交易以支持延迟追踪）。

        返回所有 confirm_date <= 指定日期 的 pending 交易，按 id 升序。
        """
        rows = self.conn.execute(
            "SELECT * FROM trades WHERE status = ? AND confirm_date <= ? ORDER BY id",
            ("pending", confirm_date.isoformat()),
        ).fetchall()
        return [_row_to_trade(r) for r in rows]

    def confirm(self, trade_id: int, shares: Decimal, nav: Decimal) -> None:  # type: ignore[override]
        """将指定交易标记为已确认，并写入份额与确认用 NAV（v0.2.1：重置延迟标记）。"""
        with self.conn:
            self.conn.execute(
                """
                UPDATE trades SET
                    status = ?,
                    shares = ?,
                    nav = ?,
                    confirmation_status = 'normal',
                    delayed_reason = NULL,
                    delayed_since = NULL
                WHERE id = ?
                """,
                (
                    "confirmed",
                    _decimal_to_str(shares),
                    format(nav, "f"),
                    trade_id,
                ),
            )

    def update(self, trade: Trade) -> None:  # type: ignore[override]
        """更新交易记录（v0.2.1：支持延迟追踪字段更新）。"""
        with self.conn:
            self.conn.execute(
                """
                UPDATE trades SET
                    status = ?,
                    shares = ?,
                    confirmation_status = ?,
                    delayed_reason = ?,
                    delayed_since = ?
                WHERE id = ?
                """,
                (
                    trade.status,
                    _decimal_to_str(trade.shares),
                    trade.confirmation_status,
                    trade.delayed_reason,
                    trade.delayed_since.isoformat() if trade.delayed_since else None,
                    trade.id,
                ),
            )

    def list_recent_trades(self, days: int = 7) -> list[Trade]:  # type: ignore[override]
        """列出最近 N 天的交易（v0.2.1：用于日报展示）。"""
        rows = self.conn.execute(
            """
            SELECT * FROM trades
            WHERE trade_date >= date('now', '-' || ? || ' days')
            ORDER BY trade_date DESC, id DESC
            """,
            (days,),
        ).fetchall()
        return [_row_to_trade(r) for r in rows]

    def position_shares(self) -> dict[str, Decimal]:  # type: ignore[override]
        """按基金代码聚合已确认交易，返回净持仓份额（买入为正，卖出为负）。"""
        rows = self.conn.execute(
            "SELECT fund_code, type, shares FROM trades WHERE status = 'confirmed' AND shares IS NOT NULL"
        ).fetchall()
        position: dict[str, Decimal] = {}
        for row in rows:
            shares = Decimal(row["shares"])
            if row["type"] == "sell":
                shares = -shares
            position[row["fund_code"]] = position.get(row["fund_code"], Decimal("0")) + shares
        return position

    def skip_dca_for_date(self, fund_code: str, day: date) -> int:  # type: ignore[override]
        """将指定日期的 pending 买入定投标记为 skipped，返回影响行数。"""
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


def _decimal_to_str(value: Decimal | None) -> str | None:
    """将 Decimal 转换为字符串格式，None 原样返回。"""
    if value is None:
        return None
    return format(value, "f")


def _row_to_trade(row: sqlite3.Row) -> Trade:
    """将 trades 表的 SQLite 行记录转换为 Trade 实体。"""
    shares = row["shares"]
    confirm_date_str = row["confirm_date"]
    # v0.2.1: 使用 try-except 处理可能缺失的新字段（向后兼容）
    try:
        confirmation_status = row["confirmation_status"] or "normal"
        delayed_reason = row["delayed_reason"]
        delayed_since_str = row["delayed_since"]
    except (KeyError, IndexError):
        confirmation_status = "normal"
        delayed_reason = None
        delayed_since_str = None

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
        pricing_date=date.fromisoformat(row["pricing_date"]) if row["pricing_date"] else None,
        confirm_date=date.fromisoformat(confirm_date_str) if confirm_date_str else None,
        # v0.2.1: 确认延迟追踪字段
        confirmation_status=confirmation_status,
        delayed_reason=delayed_reason,
        delayed_since=date.fromisoformat(delayed_since_str) if delayed_since_str else None,
    )
