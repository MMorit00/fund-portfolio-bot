"""定投相关业务流程。"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime

from src.core.dependency import dependency
from src.core.models import ActionLog, DcaPlan
from src.data.db.action_repo import ActionRepo
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
    生成当天应执行的定投 pending 交易（v0.3.4+：短月自动顺延）。

    规则：
    - daily: 每日生成
    - weekly: rule = MON/TUE/WED/THU/FRI
    - monthly: rule = 1..31（若当月无该日，顺延到月末最后一天）

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
                _log_action=False,  # DCA 自动执行不记录行为日志
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
    note: str | None = None,
    trade_repo: TradeRepo | None = None,
    action_repo: ActionRepo | None = None,
) -> int:
    """
    将指定基金在某日的定投标记为 skipped。

    MVP 简化：依赖 TradeRepo 在该日生成的 pending 定投交易进行状态更新。

    Args:
        fund_code: 基金代码。
        day: 目标日期（仅影响当日、类型为 buy、状态为 pending 的记录）。
        note: 人话备注（为什么跳过）。
        trade_repo: 交易仓储（可选，自动注入）。
        action_repo: 行为日志仓储（可选，自动注入）。

    Returns:
        受影响的记录数。
    """
    # trade_repo 已通过装饰器自动注入
    affected = trade_repo.skip_dca_for_date(fund_code, day)

    # 记录行为日志（用户主动决定跳过定投）
    if affected > 0 and action_repo is not None:
        action_repo.add(
            ActionLog(
                id=None,
                action="dca_skip",
                actor="human",
                acted_at=datetime.now(),
                trade_id=None,  # 可能影响多条，不关联具体 trade
                intent=None,
                note=note or f"{fund_code} @ {day}",
            )
        )

    return affected


# ========== 私有辅助函数 ==========


def _is_plan_due(plan: DcaPlan, day: date) -> bool:
    """
    判断定投计划在指定日期是否到期（v0.3.4+：月度定投支持短月顺延）。

    月度定投规则：
    - 若 rule=31 但当月只有 28/29/30 天，则在月末最后一天触发
    - 示例：rule=31 在 2 月 28 日（非闰年）触发
    """
    if plan.frequency == "daily":
        return True
    if plan.frequency == "weekly":
        weekday_map = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
        return plan.rule.upper() == weekday_map[day.weekday()]
    if plan.frequency == "monthly":
        try:
            target_day = int(plan.rule)
            # 短月顺延到月末最后一天
            _, last_day = monthrange(day.year, day.month)
            effective_day = min(target_day, last_day)
            return day.day == effective_day
        except ValueError:
            return False
    return False
