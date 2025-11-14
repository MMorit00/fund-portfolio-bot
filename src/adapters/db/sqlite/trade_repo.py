from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from src.core.trade import Trade
from src.usecases.ports import TradeRepo


class SqliteTradeRepo(TradeRepo):
    """
    SQLite 实现（占位）。
    TODO: 注入连接/DB helper；实现 add/list_pending_to_confirm/confirm/position_shares。
    """

    def __init__(self) -> None:
        pass

    def add(self, trade: Trade) -> Trade:  # type: ignore[override]
        raise NotImplementedError

    def list_pending_to_confirm(self, confirm_date: date) -> List[Trade]:  # type: ignore[override]
        raise NotImplementedError

    def confirm(self, trade_id: int, shares: Decimal, nav: Decimal) -> None:  # type: ignore[override]
        raise NotImplementedError

    def position_shares(self) -> Dict[str, Decimal]:  # type: ignore[override]
        raise NotImplementedError

