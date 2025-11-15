from __future__ import annotations

from datetime import date

from src.usecases.ports import DcaPlanRepo, TradeRepo


class SkipDcaForDate:
    """
    将指定基金在某日的定投标记为 skipped。
    MVP 简化：依赖 TradeRepo 在该日生成的 pending 定投交易进行状态更新。
    """

    def __init__(self, dca_repo: DcaPlanRepo, trade_repo: TradeRepo) -> None:
        self.dca_repo = dca_repo
        self.trade_repo = trade_repo

    def execute(self, *, fund_code: str, day: date) -> int:
        """返回被标记为 skipped 的条目数量。实现细节由仓储承担。"""
        return self.trade_repo.skip_dca_for_date(fund_code, day)
