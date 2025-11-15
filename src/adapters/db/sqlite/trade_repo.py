from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from src.core.trade import Trade
from src.core.trading.settlement import get_confirm_date
from src.usecases.ports import TradeRepo


def _decimal_to_str(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return format(value, "f")


def _row_to_trade(row: sqlite3.Row) -> Trade:
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


class SqliteTradeRepo(TradeRepo):
    """SQLite 交易仓储实现。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(self, trade: Trade) -> Trade:  # type: ignore[override]
        confirm_day = get_confirm_date(trade.market, trade.trade_date)
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
        rows = self.conn.execute(
            "SELECT * FROM trades WHERE status = ? AND confirm_date = ? ORDER BY id",
            ("pending", confirm_date.isoformat()),
        ).fetchall()
        return [_row_to_trade(r) for r in rows]

    def confirm(self, trade_id: int, shares: Decimal, nav: Decimal) -> None:  # type: ignore[override]
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
