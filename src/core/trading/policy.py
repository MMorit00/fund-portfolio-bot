from __future__ import annotations

from dataclasses import dataclass

from src.core.trade import MarketType


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


def default_policy(market: MarketType) -> SettlementPolicy:
    """按市场返回默认结算策略（可被基金级覆盖）。

    当前默认：
    - A：定价/计数=CN_A，T+1；无 guard。
    - QDII：定价/计数=US_NYSE，T+2；guard=CN_A（国内渠道开门约束）。
    """

    if market == "A":
        return SettlementPolicy(
            pricing_calendar="CN_A",
            settle_lag=1,
            lag_counting_calendar="CN_A",
            guard_calendar=None,
        )
    # 默认将 QDII 视为美股定价、T+2，受 A 股渠道日历 guard
    return SettlementPolicy(
        pricing_calendar="US_NYSE",
        settle_lag=2,
        lag_counting_calendar="US_NYSE",
        guard_calendar="CN_A",
    )

