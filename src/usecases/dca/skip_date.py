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
        """
        将指定基金在给定日期的定投买入（pending）标记为 skipped。

        Args:
            fund_code: 基金代码。
            day: 目标日期（仅影响当日、类型为 buy、状态为 pending 的记录）。

        Returns:
            受影响的记录数。
        """
        return self.trade_repo.skip_dca_for_date(fund_code, day)
