from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.core.dca.plan import DcaPlan
from src.core.trading.trade import Trade
from src.usecases.ports import DcaPlanRepo, FundRepo, TradeRepo


class RunDailyDca:
    """
    生成当天应执行的定投 pending 交易。

    规则：
    - daily: 每日生成
    - weekly: rule = MON/TUE/WED/THU/FRI
    - monthly: rule = 1..31（若当月无该日，顺延到月末可留 TODO）
    """

    def __init__(self, dca_repo: DcaPlanRepo, fund_repo: FundRepo, trade_repo: TradeRepo) -> None:
        self.dca_repo = dca_repo
        self.fund_repo = fund_repo
        self.trade_repo = trade_repo

    def _due(self, plan: DcaPlan, day: date) -> bool:
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

    def execute(self, *, today: date) -> int:
        plans = self.dca_repo.list_due_plans(today)
        count = 0
        for p in plans:
            if not self._due(p, today):
                continue
            fund = self.fund_repo.get_fund(p.fund_code)
            if not fund:
                continue
            t = Trade(
                id=None,
                fund_code=p.fund_code,
                type="buy",
                amount=p.amount,
                trade_date=today,
                status="pending",
                market=fund.get("market", "A"),
            )
            self.trade_repo.add(t)
            count += 1
        return count

