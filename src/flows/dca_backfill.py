"""DCA 回填逻辑（v0.4.3）。

用途：
- 将历史导入的交易标记为 DCA 归属（trades.dca_plan_key）
- 更新行为日志策略标签（action_log.strategy）
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from src.core.dependency import dependency
from src.core.log import log
from src.core.models import BackfillMatch, BackfillResult, FundBackfillSummary
from src.core.models.dca_plan import DcaPlan
from src.data.db.action_repo import ActionRepo
from src.data.db.dca_plan_repo import DcaPlanRepo
from src.data.db.trade_repo import TradeRepo


@dependency
def backfill_dca_for_batch(
    *,
    batch_id: int,
    mode: str = "dry_run",
    fund_code: str | None = None,
    trade_repo: TradeRepo | None = None,
    action_repo: ActionRepo | None = None,
    dca_plan_repo: DcaPlanRepo | None = None,
) -> BackfillResult:
    """
    为指定导入批次的交易回填 DCA 归属（v0.4.3）。

    回填逻辑：
    1. 查询批次内的所有 buy 交易；
    2. 按 fund_code 分组，对每只基金：
       - 查询其 DCA 计划（active + disabled）；
       - 对每笔交易检查是否匹配 DCA 规则（日期+金额）；
       - 匹配成功 → 标记 dca_plan_key = fund_code。
    3. apply 模式：批量更新 trades.dca_plan_key 和 action_log.strategy。

    Args:
        batch_id: 导入批次 ID（作用范围）。
        mode: 运行模式，"dry_run" 或 "apply"。
        fund_code: 可选的基金代码过滤（None=全部）。
        trade_repo: 交易仓储。
        action_repo: 行为日志仓储。
        dca_plan_repo: 定投计划仓储。

    Returns:
        BackfillResult：回填结果汇总。
    """
    # 1. 查询批次交易（只处理 buy）
    log(f"[Backfill] 正在分析批次 {batch_id} 的交易...")
    all_trades = trade_repo.list_by_batch(batch_id, fund_code)
    buy_trades = [t for t in all_trades if t.type == "buy"]

    if not buy_trades:
        log(f"[Backfill] 批次 {batch_id} 没有买入交易")
        return BackfillResult(
            batch_id=batch_id,
            mode=mode,
            total_trades=0,
            matched_count=0,
            fund_code_filter=fund_code,
        )

    log(f"[Backfill] 发现 {len(buy_trades)} 笔买入交易")

    # 2. 按基金分组
    trades_by_fund: dict[str, list] = defaultdict(list)
    for trade in buy_trades:
        trades_by_fund[trade.fund_code].append(trade)

    log(f"[Backfill] 涉及 {len(trades_by_fund)} 只基金")

    # 3. 对每只基金进行匹配分析
    fund_summaries: list[FundBackfillSummary] = []
    all_matched_trade_ids: list[int] = []

    for code, trades in sorted(trades_by_fund.items()):
        # 3.1 查询该基金的 DCA 计划
        plans = dca_plan_repo.list_by_fund(code)

        if not plans:
            # 没有定投计划，跳过
            fund_summaries.append(
                FundBackfillSummary(
                    fund_code=code,
                    total_trades=len(trades),
                    matched_trades=0,
                    has_dca_plan=False,
                )
            )
            continue

        # 3.2 使用第一个计划作为匹配规则（当前约束：一只基金只有一个计划）
        plan = plans[0]
        plan_info = f"{plan.amount} 元/{plan.frequency}/{plan.rule} ({plan.status})"

        # 3.3 对每笔交易进行匹配
        matches: list[BackfillMatch] = []
        for trade in trades:
            if trade.id is None:
                continue

            is_match, reason = _is_dca_match(
                trade.trade_date,
                trade.amount,
                plan,
            )

            matches.append(
                BackfillMatch(
                    trade_id=trade.id,
                    fund_code=trade.fund_code,
                    trade_date=trade.trade_date.isoformat(),
                    amount=trade.amount,
                    matched=is_match,
                    dca_plan_key=code if is_match else None,
                    match_reason=reason,
                )
            )

            if is_match:
                all_matched_trade_ids.append(trade.id)

        matched_count = sum(1 for m in matches if m.matched)
        fund_summaries.append(
            FundBackfillSummary(
                fund_code=code,
                total_trades=len(trades),
                matched_trades=matched_count,
                has_dca_plan=True,
                dca_plan_info=plan_info,
                matches=matches,
            )
        )

    # 4. apply 模式：执行更新
    updated_count = 0
    if mode == "apply" and all_matched_trade_ids:
        log(f"[Backfill] 开始回填 {len(all_matched_trade_ids)} 笔匹配交易...")

        # 按基金分组更新（因为 dca_plan_key = fund_code）
        for summary in fund_summaries:
            if summary.matched_trades == 0:
                continue
            matched_ids = [m.trade_id for m in summary.matches if m.matched]
            if matched_ids:
                # 更新 trades.dca_plan_key
                rows = trade_repo.update_dca_plan_key_bulk(matched_ids, summary.fund_code)
                updated_count += rows
                log(f"[Backfill] {summary.fund_code}: 更新 {rows} 笔交易")

        # 更新 action_log.strategy
        if all_matched_trade_ids:
            action_rows = action_repo.update_strategy_by_trade_ids(all_matched_trade_ids, "dca")
            log(f"[Backfill] 更新 {action_rows} 条 action_log 记录")

    return BackfillResult(
        batch_id=batch_id,
        mode=mode,
        total_trades=len(buy_trades),
        matched_count=len(all_matched_trade_ids),
        updated_count=updated_count,
        fund_summaries=fund_summaries,
        fund_code_filter=fund_code,
    )


def _is_dca_match(
    trade_date: date,
    trade_amount: Decimal,
    plan: DcaPlan,
) -> tuple[bool, str]:
    """
    判断交易是否匹配定投计划。

    Returns:
        (is_match, reason): 是否匹配 + 原因说明。
    """
    # 1. 日期匹配
    if plan.frequency == "daily":
        date_match = True
        date_reason = "daily（任意交易日）"

    elif plan.frequency == "weekly":
        weekday_map = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
        expected = plan.rule  # "MON"
        actual = weekday_map[trade_date.weekday()]
        date_match = (actual == expected)
        date_reason = f"weekly: {actual} {'==' if date_match else '!='} {expected}"

    elif plan.frequency == "monthly":
        expected_day = int(plan.rule)  # 10
        actual_day = trade_date.day
        # 处理短月：31号计划在30天月份也能匹配月末
        if expected_day > 28:
            # 计算当月最后一天
            next_month = trade_date.replace(day=28) + timedelta(days=4)
            last_day = (next_month.replace(day=1) - timedelta(days=1)).day
            date_match = (actual_day == expected_day or
                         (actual_day == last_day and expected_day > last_day))
            date_reason = f"monthly: {actual_day} vs {expected_day} (last_day={last_day})"
        else:
            date_match = (actual_day == expected_day)
            date_reason = f"monthly: {actual_day} {'==' if date_match else '!='} {expected_day}"

    else:
        date_match = False
        date_reason = f"未知频率: {plan.frequency}"

    # 2. 金额匹配（允许 ±10% 浮动）
    tolerance = Decimal("0.1")
    lower = plan.amount * (Decimal("1") - tolerance)
    upper = plan.amount * (Decimal("1") + tolerance)
    amount_match = (lower <= trade_amount <= upper)

    if amount_match:
        amount_reason = f"金额匹配: {trade_amount} ∈ [{lower}, {upper}]"
    else:
        amount_reason = f"金额不符: {trade_amount} ∉ [{lower}, {upper}]"

    # 3. 综合判断
    is_match = date_match and amount_match
    reason = f"{date_reason}; {amount_reason}"

    return is_match, reason
