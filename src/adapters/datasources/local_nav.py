from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.core.protocols import NavProtocol, NavRepo


class LocalNavService(NavProtocol):
    """
    本地 NAV 查询服务：从 NavRepo 读取官方单位净值。

    职责：
    - 作为运行时 NAV 查询服务，被用例（确认/日报/再平衡）调用；
    - 不发起外部 HTTP，仅从本地 `navs` 表读取数据；
    - 数据写入由独立 Job（如 `fetch_navs`）负责。
    """

    def __init__(self, nav_repo: NavRepo) -> None:
        self.nav_repo = nav_repo

    def get_nav(self, fund_code: str, day: date) -> Decimal | None:
        """从本地 NavRepo 获取指定日期的净值。"""
        return self.nav_repo.get(fund_code, day)

