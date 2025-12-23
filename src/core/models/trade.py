from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Literal

TradeType = Literal["buy", "sell"]
TradeStatus = Literal["pending", "confirmed", "skipped"]


class MarketType(str, Enum):
    """
    市场类型枚举（使用标准市场标识）。

    说明：
    - 继承自 str，保持与数据库中的字符串值兼容；
    - __str__ 返回枚举值本身，便于日志与 CLI 展示；
    - 当前内建市场：CN_A（国内 A 股）、US_NYSE（美股 NYSE）。
    """

    CN_A = "CN_A"
    US_NYSE = "US_NYSE"


@dataclass(slots=True)
class Trade:
    """
    交易实体。

    说明：
    - 金额/份额均使用 Decimal，禁止 float；
    - confirmation_status / delayed_reason / delayed_since 用于跟踪确认延迟状态；
    - external_id 用于历史导入去重（外部订单号等）。
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

    confirmation_status: str = "normal"      # normal / delayed
    delayed_reason: str | None = None        # nav_missing / unknown
    delayed_since: date | None = None        # 首次延迟日期

    external_id: str | None = None           # 外部唯一标识（支付宝订单号等）
    import_batch_id: int | None = None       # 导入批次 ID（仅历史导入填写）
    dca_plan_key: str | None = None          # 定投计划标识（当前格式=fund_code）

    # v16: 账单导入扩展字段
    fee: Decimal | None = None               # 手续费
    apply_amount: Decimal | None = None      # 申请金额
    apply_shares: Decimal | None = None      # 申请份额（预留）
