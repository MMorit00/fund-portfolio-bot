from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from src.core.models import MarketType, SettlementPolicy

if TYPE_CHECKING:
    from src.data.db.calendar import CalendarService


def calc_pricing_date(trade_date: date, policy: SettlementPolicy, calendar: "CalendarService") -> date:
    """
    计算定价日（策略版）：先过 guard（若有），再在定价日历上取下一开市日。

    参数：
        trade_date: 下单/约定日。
        policy: 结算策略（含 guard 与定价/计数日历）。
        calendar: 交易日历服务。
    """
    effective = calendar.next_open(policy.guard_calendar, trade_date) if policy.guard_calendar else trade_date
    return calendar.next_open(policy.pricing_calendar, effective)


def calc_settlement_dates(trade_date: date, policy: SettlementPolicy, calendar: "CalendarService") -> tuple[date, date]:
    """返回 (pricing_date, confirm_date)，计数在 `lag_counting_calendar` 上进行。"""
    pricing = calc_pricing_date(trade_date, policy, calendar)
    confirm = calendar.shift(policy.lag_counting_calendar, pricing, policy.settle_lag)
    return pricing, confirm


def default_policy(market: MarketType) -> SettlementPolicy:
    """
    按市场返回默认结算策略（系统内建规则）。

    当前默认：
    - CN_A：定价/计数=CN_A，T+1；无 guard。
    - US_NYSE：定价/计数=US_NYSE，T+2；guard=CN_A（国内渠道开门约束）。

    注意：
    - 这是业务规则，不是环境配置。未来可通过 per-fund 策略覆盖。
    - v0.3.2：统一使用标准市场标识 CN_A/US_NYSE。

    Args:
        market: 市场类型（MarketType 枚举）。

    Returns:
        结算策略。

    Raises:
        ValueError: 不支持的市场类型。
    """
    if market is MarketType.CN_A:
        return SettlementPolicy(
            pricing_calendar=MarketType.CN_A.value,
            settle_lag=1,
            lag_counting_calendar=MarketType.CN_A.value,
            guard_calendar=None,
        )
    if market is MarketType.US_NYSE:
        return SettlementPolicy(
            pricing_calendar=MarketType.US_NYSE.value,
            settle_lag=2,
            lag_counting_calendar=MarketType.US_NYSE.value,
            guard_calendar=MarketType.CN_A.value,
        )
    raise ValueError(f"不支持的市场类型：{market}（仅支持 CN_A / US_NYSE）")
