"""定投相关业务流程。"""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from src.core.models.dca_plan import DcaPlan
from src.flows.trade import CreateTrade

if TYPE_CHECKING:
    from src.data.db.dca_plan_repo import DcaPlanRepo
    from src.data.db.trade_repo import TradeRepo
class RunDailyDca:
    """
    生成当天应执行的定投 pending 交易。

    规则：
    - daily: 每日生成
    - weekly: rule = MON/TUE/WED/THU/FRI
    - monthly: rule = 1..31（若当月无该日，顺延到月末可留 TODO）
    """

    def __init__(self, dca_repo: "DcaPlanRepo", create_trade: CreateTrade) -> None:
        self.dca_repo = dca_repo
        self.create_trade = create_trade

    def execute(self, *, today: date) -> int:
        """
        生成当天应执行的定投 pending 交易。

        Args:
            today: 当日日期；按计划频率/规则判断是否到期。

        Returns:
            生成的交易数量。
        """
        plans = self.dca_repo.list_due_plans(today)
        count = 0
        for p in plans:
            if not self._due(p, today):
                continue
            try:
                self.create_trade.execute(
                    fund_code=p.fund_code,
                    trade_type="buy",
                    amount=p.amount,
                    trade_day=today,
                )
                count += 1
            except ValueError:
                # 基金不存在或配置无效，跳过
                continue
        return count

    def _due(self, plan: DcaPlan, day: date) -> bool:
        """判断定投计划在指定日期是否到期。"""
        if plan.frequency == "daily":
            return True
        if plan.frequency == "weekly":
            weekday_map = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
            return plan.rule.upper() == weekday_map[day.weekday()]
        if plan.frequency == "monthly":
            try:
                return int(plan.rule) == day.day
            except ValueError:
                return False
        return False




class SkipDca:
    """
    将指定基金在某日的定投标记为 skipped。
    MVP 简化：依赖 TradeRepo 在该日生成的 pending 定投交易进行状态更新。
    """

    def __init__(self, dca_repo: "DcaPlanRepo", trade_repo: "TradeRepo") -> None:
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
