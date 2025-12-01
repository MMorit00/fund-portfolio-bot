from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

TradeType = Literal["buy", "sell"]
TradeStatus = Literal["pending", "confirmed", "skipped"]
MarketType = Literal["CN_A", "US_NYSE"]  # v0.3.2：统一使用标准市场标识


@dataclass(slots=True)
class Trade:
    """
    交易实体（MVP 简化版）。

    注意：金额/份额均使用 Decimal，禁止 float。

    确认延迟追踪（v0.2.1）：
    - confirmation_status: 确认状态（normal/delayed）
    - delayed_reason: 延迟原因（nav_missing/unknown）
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
    pricing_date: date | None = None
    confirm_date: date | None = None

    # v0.2.1: 确认延迟追踪
    confirmation_status: str = "normal"      # normal / delayed
    delayed_reason: str | None = None        # nav_missing / unknown
    delayed_since: date | None = None        # 首次延迟日期

    # v0.4.2: 历史导入去重
    external_id: str | None = None           # 外部唯一标识（支付宝订单号等）
