from __future__ import annotations

from datetime import date

from src.core.trade import MarketType
from src.core.trading.calendar import TradingCalendar


def get_confirm_date(market: MarketType, trade_date: date, calendar: TradingCalendar) -> date:
    """
    计算确认日期（v0.2）：基于“定价日 + lag”的规则。

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
