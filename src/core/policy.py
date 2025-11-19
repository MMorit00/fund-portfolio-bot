from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SettlementPolicy:
    """
    结算策略对象（Policy Object）。

    用于明确一只基金（或一个市场默认）的交易日口径：
    - pricing_calendar: 定价所依赖的交易所日历（如 "CN_A"、"US_NYSE"）。
    - settle_lag: 确认滞后天数（如 A=1, QDII=2）。
    - lag_counting_calendar: 用于计数 T+N 的日历（一般与定价市场一致）。
    - guard_calendar: 前置卫兵日历（如国内渠道/银行日历）；若为空则不启用卫兵。
    """

    pricing_calendar: str
    settle_lag: int
    lag_counting_calendar: str
    guard_calendar: str | None = None
