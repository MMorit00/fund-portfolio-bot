"""定投相关业务流程。"""

from __future__ import annotations

from datetime import date

from src.core.dependency import dependency
from src.core.models.dca_plan import DcaPlan
from src.data.db.dca_plan_repo import DcaPlanRepo
from src.data.db.trade_repo import TradeRepo
from src.flows.trade import create_trade


@dependency
def run_daily_dca(
    *,
    today: date,
    dca_plan_repo: DcaPlanRepo | None = None,
) -> int:
    """
    生成当天应执行的定投 pending 交易（v0.3.2：仅处理 active 计划）。

    规则：
    - daily: 每日生成
    - weekly: rule = MON/TUE/WED/THU/FRI
    - monthly: rule = 1..31（若当月无该日，顺延到月末可留 TODO）

    Args:
        today: 当日日期；按计划频率/规则判断是否到期。
        dca_plan_repo: 定投计划仓储（可选，自动注入）。

    Returns:
        生成的交易数量。
    """
    # dca_plan_repo 已通过装饰器自动注入
    # v0.3.2：仅获取活跃计划（status='active'）
    plans = dca_plan_repo.list_active()
    count = 0
    for p in plans:
        if not _is_plan_due(p, today):
            continue
        try:
            create_trade(
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


@dependency
def skip_dca(
    *,
    fund_code: str,
    day: date,
    trade_repo: TradeRepo | None = None,
) -> int:
    """
    将指定基金在某日的定投标记为 skipped。

    MVP 简化：依赖 TradeRepo 在该日生成的 pending 定投交易进行状态更新。

    Args:
        fund_code: 基金代码。
        day: 目标日期（仅影响当日、类型为 buy、状态为 pending 的记录）。
        trade_repo: 交易仓储（可选，自动注入）。

    Returns:
        受影响的记录数。
    """
    # trade_repo 已通过装饰器自动注入
    return trade_repo.skip_dca_for_date(fund_code, day)


# ========== 私有辅助函数 ==========


def _is_plan_due(plan: DcaPlan, day: date) -> bool:
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
