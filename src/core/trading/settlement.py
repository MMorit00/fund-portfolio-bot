from __future__ import annotations

from datetime import date, timedelta
from typing import Literal


MarketType = Literal["A", "QDII"]


def get_confirm_date(market: MarketType, trade_date: date) -> date:
    """
    返回该笔交易的确认日期（MVP 仅处理工作日简单规则）。

    - A 股：T+1（若遇周末顺延到下一个周一）
    - QDII：T+2（若遇周末顺延到下一个周一/周二）

    TODO-holiday: 后续补充法定节假日顺延规则与交易日历。
    """

    offset = 1 if market == "A" else 2
    d = trade_date + timedelta(days=offset)
    # 简化：周六/周日顺延到下周一
    while d.weekday() >= 5:  # 5: Saturday, 6: Sunday
        d = d + timedelta(days=1)
    return d

