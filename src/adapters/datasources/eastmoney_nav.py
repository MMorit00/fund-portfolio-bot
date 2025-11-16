from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from src.usecases.ports import NavProvider


class EastmoneyNavProvider(NavProvider):
    """
    东方财富净值数据源（占位）。
    MVP 初期可使用 httpx/requests 抓取；网络请求逻辑后续实现。
    """

    def get_nav(self, fund_code: str, day: date) -> Optional[Decimal]:  # type: ignore[override]
        """
        读取东方财富的官方单位净值（占位）。

        Args:
            fund_code: 基金代码。
            day: 净值日期。

        Returns:
            若成功获取则返回 Decimal 净值；当前占位实现始终抛出未实现。
        """
        raise NotImplementedError
