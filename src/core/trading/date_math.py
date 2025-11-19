from __future__ import annotations

from datetime import date, timedelta
from typing import Protocol


class CalendarStore(Protocol):
    """
    日历数据访问协议：按 `calendar_key`（如 "CN_A" / "US_NYSE"）查询是否开市。
    """

    def is_open(self, calendar_key: str, day: date) -> bool: ...


class DateMath(Protocol):
    """日期运算服务：基于命名日历键进行“取下一开市日与交易日偏移”。"""

    def next_open(self, calendar_key: str, day: date) -> date: ...

    def shift(self, calendar_key: str, day: date, n: int) -> date: ...


class DateMathService:
    """
    默认实现：依赖 `CalendarStore`，提供 next_open 与 shift。
    """

    def __init__(self, store: CalendarStore) -> None:
        self.store = store

    def next_open(self, calendar_key: str, day: date) -> date:
        d = day
        if self.store.is_open(calendar_key, d):
            return d

        max_attempts = 365  # 最多向后查找一年
        for _ in range(max_attempts):
            d = d + timedelta(days=1)
            if self.store.is_open(calendar_key, d):
                return d

        raise RuntimeError(
            f"未能在 {max_attempts} 天内找到开市日：calendar_key={calendar_key} start={day}"
        )

    def shift(self, calendar_key: str, day: date, n: int) -> date:
        if n < 1:
            raise ValueError("n 必须 >= 1")
        d = day
        remaining = n
        max_attempts = n * 10 + 365  # 最多查找 n*10+365 天（考虑节假日）
        attempts = 0
        while remaining > 0:
            d = d + timedelta(days=1)
            attempts += 1
            if attempts > max_attempts:
                raise RuntimeError(
                    f"未能在 {max_attempts} 天内完成 T+{n} 偏移："
                    f"calendar_key={calendar_key} start={day}"
                )
            if self.store.is_open(calendar_key, d):
                remaining -= 1
        return d

