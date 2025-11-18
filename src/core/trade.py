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

    确认延迟追踪（v0.2.1）：
    - confirmation_status: 确认状态（NORMAL/DELAYED）
    - delayed_reason: 延迟原因（NAV_MISSING/UNKNOWN）
    - delayed_since: 首次检测到延迟的日期
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

    # v0.2.1: 确认延迟追踪
    confirmation_status: str = "normal"      # normal / delayed
    delayed_reason: str | None = None        # nav_missing / unknown
    delayed_since: date | None = None        # 首次延迟日期

