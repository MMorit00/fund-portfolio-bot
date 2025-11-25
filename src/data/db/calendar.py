from __future__ import annotations

import sqlite3
from datetime import date, timedelta


class CalendarService:
    """
    基于 SQLite 的交易日历服务实现。

    职责：
    - 实现 CalendarProtocol 的所有方法（is_open / next_open / shift）
    - 从 trading_calendar 表读取交易日历数据
    - 提供严格的日历查询，缺失数据时抛错（v0.3 严格模式）

    约定：
    - 表结构：trading_calendar(market TEXT, day TEXT, is_trading_day INTEGER)
    - PRIMARY KEY(market, day)；is_trading_day 取值 0/1
    - calendar_key 使用 market 列（如 "CN_A" / "US_NYSE"）

    缺失处理：
    - 严格模式：若缺失记录则直接抛错，要求通过"注油/修补"任务维护完整日历数据
    - 不再回退到"工作日近似"，确保数据准确性
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._validate_table_exists()

    def is_open(self, calendar_key: str, day: date) -> bool:
        """
        判断指定日期是否为交易日。

        Args:
            calendar_key: 日历标识（如 "CN_A"、"US_NYSE"）
            day: 待判断的日期

        Returns:
            True 表示交易日，False 表示休市日

        Raises:
            RuntimeError: 若 trading_calendar 表中缺失该日期的记录
        """
        row = self.conn.execute(
            "SELECT is_trading_day FROM trading_calendar WHERE market = ? AND day = ?",
            (calendar_key, day.isoformat()),
        ).fetchone()
        if row is None:
            raise RuntimeError(
                f"trading_calendar 缺失记录：calendar_key={calendar_key} day={day.isoformat()}\n"
                f"请运行 sync_calendar 或 patch_calendar 任务补充日历数据"
            )
        return int(row[0]) == 1

    def next_open(self, calendar_key: str, day: date) -> date:
        """
        返回 >= day 的首个交易日（含当日）。

        or_self 语义：如果 day 本身是交易日，返回 day；否则向后找最近的交易日。

        Args:
            calendar_key: 日历标识
            day: 参考日期

        Returns:
            首个交易日

        Raises:
            RuntimeError: 若在 365 天内未找到交易日或遇到数据缺失
        """
        d = day
        if self.is_open(calendar_key, d):
            return d

        max_attempts = 365
        for _ in range(max_attempts):
            d = d + timedelta(days=1)
            if self.is_open(calendar_key, d):
                return d

        raise RuntimeError(
            f"未能在 {max_attempts} 天内找到开市日：calendar_key={calendar_key} start={day}"
        )

    def shift(self, calendar_key: str, day: date, n: int) -> date:
        """
        从 day 向后偏移 n 个交易日（T+N）。

        无论 day 是否开市，都从 day 往后数 n 个"交易日"。
        用于计算确认日等场景：confirm_date = calendar.shift(key, pricing_date, settle_lag)。

        Args:
            calendar_key: 日历标识
            day: 起始日期
            n: 偏移量（必须 >= 1）

        Returns:
            偏移后的交易日

        Raises:
            ValueError: 若 n < 1
            RuntimeError: 若在合理范围内未能完成偏移或遇到数据缺失
        """
        if n < 1:
            raise ValueError("n 必须 >= 1")

        d = day
        remaining = n
        max_attempts = n * 10 + 365
        attempts = 0

        while remaining > 0:
            d = d + timedelta(days=1)
            attempts += 1
            if attempts > max_attempts:
                raise RuntimeError(
                    f"未能在 {max_attempts} 天内完成 T+{n} 偏移："
                    f"calendar_key={calendar_key} start={day}"
                )
            if self.is_open(calendar_key, d):
                remaining -= 1

        return d

    def prev_open(self, calendar_key: str, day: date, lookback: int = 15) -> date | None:
        """
        查找 day 之前最近的交易日（与 next_open 对称）。

        从 day - 1 开始向前查找，最多回溯 lookback 天。

        Args:
            calendar_key: 日历标识（如 "CN_A"）
            day: 参考日期
            lookback: 向前查找天数（默认 15 天，覆盖春节/国庆等长假）

        Returns:
            最近的交易日，若 lookback 天内无交易日则返回 None

        Raises:
            RuntimeError: 若 trading_calendar 表中缺失记录
        """
        d = day - timedelta(days=1)
        for _ in range(lookback):
            if d < date(2020, 1, 1):  # 防止无限回溯到过早日期
                return None
            if self.is_open(calendar_key, d):
                return d
            d = d - timedelta(days=1)
        return None

    def _validate_table_exists(self) -> None:
        """
        验证 trading_calendar 表是否存在。

        Raises:
            RuntimeError: 若 trading_calendar 表不存在，提示用户执行初始化任务
        """
        exists = (
            self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='trading_calendar'"
            ).fetchone()
            is not None
        )
        if not exists:
            raise RuntimeError(
                "v0.3 要求使用 DB 交易日历，但未发现 trading_calendar 表。\n"
                "请先执行以下任务之一来初始化交易日历：\n"
                "- sync_calendar: 同步完整日历数据\n"
                "- patch_calendar: 修补缺失的日历数据"
            )
