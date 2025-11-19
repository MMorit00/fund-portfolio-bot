from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List

from src.core.protocols import FundRepo, NavRepo, NavSourceProtocol


@dataclass(slots=True)
class FetchNavsResult:
    """
    抓取某一日官方单位净值的结果汇总。

    - day: 目标日期；
    - total: 参与抓取的基金数量；
    - success: 成功写入的数量；
    - failed_codes: 获取失败或无效 NAV（None/<=0）的基金代码列表。
    """

    day: date
    total: int
    success: int
    failed_codes: List[str]


class FetchNavsForDay:
    """
    遍历当前已配置基金，按指定日期调用外部 NavProvider 获取单位净值并落库。

    口径：
    - 仅抓取“指定日”的官方单位净值（严格版，不做回退）；
    - 成功条件：provider 返回 Decimal 且 > 0；否则视为失败；
    - 落库：调用 NavRepo.upsert(fund_code, day, nav)，按 (fund_code, day) 幂等。
    """

    def __init__(self, fund_repo: FundRepo, nav_repo: NavRepo, provider: NavSourceProtocol) -> None:
        self.fund_repo = fund_repo
        self.nav_repo = nav_repo
        self.provider = provider

    def execute(self, *, day: date) -> FetchNavsResult:
        funds = self.fund_repo.list_funds()
        total = len(funds)
        success = 0
        failed_codes: List[str] = []

        for f in funds:
            code = f.fund_code
            nav = self.provider.get_nav(code, day)
            if nav is None or nav <= Decimal("0"):
                failed_codes.append(code)
                continue
            self.nav_repo.upsert(code, day, nav)
            success += 1

        return FetchNavsResult(day=day, total=total, success=success, failed_codes=failed_codes)
