from __future__ import annotations

from datetime import date, timedelta
from typing import Protocol

from src.core.trade import MarketType


class TradingCalendar(Protocol):
    """
    交易日历协议（v0.2）：

    - is_trading_day(day): 判断给定日期是否为交易日。
    - next_trading_day(day, offset): 从给定日期起，向后数 offset 个交易日，返回目标交易日。
    - next_trading_day_or_self(day): 若给定日为交易日则返回自身，否则返回下一个交易日。

    说明：
    - 现阶段仅区分市场 A / QDII，用于后续引入市场维度的节假日与规则差异。
    - v0.2 的默认实现仅处理周末，后续可替换为“读取节假日表”的实现。
    """

    def is_trading_day(self, day: date, *, market: MarketType) -> bool: ...

    def next_trading_day(self, day: date, *, market: MarketType, offset: int = 1) -> date: ...

    def next_trading_day_or_self(self, day: date, *, market: MarketType) -> date: ...


class SimpleTradingCalendar:
    """
    简易交易日历实现：
    - 仅将周六/周日视为非交易日；除周末外均为交易日。
    - 不区分 A/QDII 的节假日差异（v0.2 范围内）。
    """

    def is_trading_day(self, day: date, *, market: MarketType) -> bool:  # noqa: ARG002
        return day.weekday() < 5  # 0..4 = 周一..周五

    def next_trading_day(self, day: date, *, market: MarketType, offset: int = 1) -> date:  # noqa: ARG002
        if offset < 1:
            raise ValueError("offset 必须 >= 1")
        d = day
        remaining = offset
        while remaining > 0:
            d = d + timedelta(days=1)
            if self.is_trading_day(d, market=market):
                remaining -= 1
        return d

    def next_trading_day_or_self(self, day: date, *, market: MarketType) -> date:  # noqa: ARG002
        if self.is_trading_day(day, market=market):
            return day
        return self.next_trading_day(day, market=market, offset=1)

