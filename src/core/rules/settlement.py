from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from src.core.models.policy import SettlementPolicy
from src.core.models.trade import MarketType

if TYPE_CHECKING:
    from src.data.db.calendar import CalendarService


def calc_confirm_date(market: MarketType, trade_date: date, calendar: "CalendarService") -> date:
    """
    计算确认日期（v0.2）：基于"定价日 + lag"的规则。

    Args:
        market: 市场类型："A" 或 "QDII"。
        trade_date: 交易日（下单/约定日）。
        calendar: 交易日历实现（v0.2 默认仅处理周末非交易日）。

    Returns:
        确认日期：`pricing_date = next_trading_day_or_self(trade_date)`，
        `confirm_date = next_trading_day(pricing_date, offset=lag)`；其中 lag(A=1, QDII=2)。

    说明：仅处理周末为非交易日；法定节假日留待后续通过可替换的 TradingCalendar 支持。
    与 v0.1 不同，周末下单的 A 基金确认日将落到周二（更贴近实务）。
    """

    lag = 1 if market == "A" else 2
    pricing_date = calendar.next_trading_day_or_self(trade_date, market=market)
    confirm_date = calendar.next_trading_day(pricing_date, market=market, offset=lag)
    return confirm_date


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
    - A：定价/计数=CN_A，T+1；无 guard。
    - QDII：定价/计数=US_NYSE，T+2；guard=CN_A（国内渠道开门约束）。

    注意：这是业务规则，不是环境配置。未来可通过 per-fund 策略覆盖。
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
