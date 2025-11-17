from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from src.core.trade import MarketType
from src.core.trading.calendar import TradingCalendar


class SqliteTradingCalendar(TradingCalendar):
    """
    基于 SQLite 的交易日历实现。

    约定：
    - 使用表 `trading_calendar(market TEXT, day TEXT, is_trading_day INTEGER)`；
    - PRIMARY KEY(market, day)；is_trading_day 取值 0/1；
    - v0.3：QDII 暂与 A 股共用日历（缺省以 market='A' 查询）。

    缺失处理：
    - 若某日没有记录，则回退为“工作日=交易日”的简化判断，以降低数据缺口造成的中断风险。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    @staticmethod
    def _map_market(market: MarketType) -> str:
        # v0.3：QDII 暂与 A 股共用交易日历
        return "A"

    def is_trading_day(self, day: date, *, market: MarketType) -> bool:
        m = self._map_market(market)
        row = self.conn.execute(
            "SELECT is_trading_day FROM trading_calendar WHERE market = ? AND day = ?",
            (m, day.isoformat()),
        ).fetchone()
        if row is None:
            # 缺失记录时退回工作日判断
            return day.weekday() < 5
        return int(row[0]) == 1

    def next_trading_day(self, day: date, *, market: MarketType, offset: int = 1) -> date:
        if offset < 1:
            raise ValueError("offset 必须 >= 1")
        d = day
        remaining = offset
        while remaining > 0:
            d = d + timedelta(days=1)
            if self.is_trading_day(d, market=market):
                remaining -= 1
        return d

    def next_trading_day_or_self(self, day: date, *, market: MarketType) -> date:
        if self.is_trading_day(day, market=market):
            return day
        return self.next_trading_day(day, market=market, offset=1)

