from __future__ import annotations

from datetime import date

from src.core.dca_plan import DcaPlan
from src.core.protocols import DcaPlanRepo
from src.usecases.trading.create_trade import CreateTrade


class RunDailyDca:
    """
    生成当天应执行的定投 pending 交易。

    规则：
    - daily: 每日生成
    - weekly: rule = MON/TUE/WED/THU/FRI
    - monthly: rule = 1..31（若当月无该日，顺延到月末可留 TODO）
    """

    def __init__(self, dca_repo: DcaPlanRepo, create_trade: CreateTrade) -> None:
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
