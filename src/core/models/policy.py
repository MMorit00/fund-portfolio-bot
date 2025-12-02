from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SettlementPolicy:
    """
    结算日历策略。

    用于定义一只基金（或某个市场）的定价日和确认日如何计算：
    - pricing_calendar_id: 使用哪一个市场日历作为定价日历（如 "CN_A"、"US_NYSE"）；
    - settlement_lag: T+N 中的 N（如 A 股=1，QDII=2）；
    - settlement_calendar_id: 在哪一个日历上进行 T+N 计数（一般与定价市场一致）；
    - guard_calendar_id: 前置卫兵日历（如国内渠道/银行日历），为空表示不启用卫兵。
    """

    pricing_calendar_id: str
    settlement_lag: int
    settlement_calendar_id: str
    guard_calendar_id: str | None = None
