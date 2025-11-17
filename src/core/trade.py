from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

TradeType = Literal["buy", "sell"]
TradeStatus = Literal["pending", "confirmed", "skipped"]
MarketType = Literal["A", "QDII"]


@dataclass(slots=True)
class Trade:
    """
    交易实体（MVP 简化版）。

    注意：金额/份额均使用 Decimal，禁止 float。
    """

    id: int | None
    fund_code: str
    type: TradeType
    amount: Decimal
    trade_date: date
    status: TradeStatus
    market: MarketType
    shares: Decimal | None = None
    remark: str | None = None
    confirm_date: date | None = None

