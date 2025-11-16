from __future__ import annotations

from datetime import date

from src.core.trade import MarketType
from src.core.trading.calendar import TradingCalendar


def get_confirm_date(market: MarketType, trade_date: date, calendar: TradingCalendar) -> date:
    """
    计算确认日期（v0.2）：基于“定价日 + lag”的规则。

    - 定价日：pricing_date = calendar.next_trading_day_or_self(trade_date)
    - lag：A=1，QDII=2（v0.2 不做基金级覆盖）
    - 确认日：confirm_date = calendar.next_trading_day(pricing_date, offset=lag)

    说明：
    - 仅处理周末为非交易日；法定节假日留待后续通过可替换的 TradingCalendar 支持。
    - 相比 v0.1（基于 trade_date + lag 再周末顺延），周末下单的 A 基金会落到周二确认（更贴近实务）。
    """

    lag = 1 if market == "A" else 2
    pricing_date = calendar.next_trading_day_or_self(trade_date, market=market)
    confirm_date = calendar.next_trading_day(pricing_date, market=market, offset=lag)
    return confirm_date
