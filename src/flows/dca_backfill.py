"""DCA 回填逻辑（v0.4.3）。

用途：
- 将历史导入的交易标记为 DCA 归属（trades.dca_plan_key）
- 更新行为日志策略标签（action_log.strategy）
- 为 AI 提供结构化事实快照（FundDcaFacts）
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from src.core.dependency import dependency
from src.core.log import log
from src.core.models import (
    BackfillResult,
    DcaTradeCheck,
    FundBackfillSummary,
    FundDcaFacts,
    TradeFlag,
)
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

    回填逻辑（规则层只输出事实，日期+同日唯一性决定归属）：
    1. 查询批次内的所有 buy 交易；
    2. 按 fund_code 分组，对每只基金：
       - 查询其 DCA 计划（active + disabled）；
       - 对每笔交易计算 DCA 事实（日期轨道 + 金额偏差）；
       - 同一天多笔时，仅选金额偏差最小的一笔作为该天的 DCA 执行；
       - 标记 dca_plan_key = fund_code（仅对选中笔）。
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

        # 3.3 对每笔交易计算 DCA 事实
        # 先计算所有交易的事实
        trade_facts: list[tuple] = []  # (trade, date_match, amount_deviation, reason)
        for trade in trades:
            if trade.id is None:
                continue
            date_match, amount_deviation, reason = _calc_dca_facts(
                trade.trade_date,
                trade.amount,
                plan,
            )
            trade_facts.append((trade, date_match, amount_deviation, reason))

        # 3.4 同一天多笔买入时，只选金额最接近的一笔（定投每天最多执行一次）
        selected_ids: set[int] = set()
        trades_by_date: dict[date, list[tuple]] = defaultdict(list)
        for item in trade_facts:
            trade, date_match, _, _ = item
            if date_match:
                trades_by_date[trade.trade_date].append(item)

        for same_day_trades in trades_by_date.values():
            if len(same_day_trades) == 1:
                # 当天只有一笔，直接选中
                selected_ids.add(same_day_trades[0][0].id)
            else:
                # 当天多笔，选金额偏差绝对值最小的
                best = min(same_day_trades, key=lambda x: abs(x[2]))
                selected_ids.add(best[0].id)

        # 3.5 生成匹配结果
        checks: list[DcaTradeCheck] = []
        for trade, date_match, amount_deviation, reason in trade_facts:
            # 归属条件：日期匹配 + 被选中（同一天只选一笔）
            is_selected = trade.id in selected_ids
            if date_match and not is_selected:
                reason = f"{reason} [同日有更接近的交易]"

            checks.append(
                DcaTradeCheck(
                    trade_id=trade.id,
                    fund_code=trade.fund_code,
                    trade_date=trade.trade_date.isoformat(),
                    amount=trade.amount,
                    matched=is_selected,
                    amount_deviation=amount_deviation,
                    dca_plan_key=code if is_selected else None,
                    match_reason=reason,
                )
            )

            if is_selected:
                all_matched_trade_ids.append(trade.id)

        matched_count = sum(1 for c in checks if c.matched)
        fund_summaries.append(
            FundBackfillSummary(
                fund_code=code,
                total_trades=len(trades),
                matched_trades=matched_count,
                has_dca_plan=True,
                dca_plan_info=plan_info,
                matches=checks,
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


def _calc_dca_facts(
    trade_date: date,
    trade_amount: Decimal,
    plan: DcaPlan,
) -> tuple[bool, Decimal, str]:
    """
    计算交易的 DCA 匹配事实（规则层只输出事实，不做语义判断）。

    Returns:
        (date_match, amount_deviation, reason):
        - date_match: 日期是否在 DCA 轨道上
        - amount_deviation: 金额偏差率（正=超出计划，负=低于计划）
        - reason: 事实说明
    """
    # 1. 日期匹配（决定归属）
    if plan.frequency == "daily":
        date_match = True
        date_reason = "daily"

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
            next_month = trade_date.replace(day=28) + timedelta(days=4)
            last_day = (next_month.replace(day=1) - timedelta(days=1)).day
            date_match = (actual_day == expected_day or
                         (actual_day == last_day and expected_day > last_day))
            date_reason = f"monthly: {actual_day} vs {expected_day}"
        else:
            date_match = (actual_day == expected_day)
            date_reason = f"monthly: {actual_day} {'==' if date_match else '!='} {expected_day}"

    else:
        date_match = False
        date_reason = f"未知频率: {plan.frequency}"

    # 2. 金额偏差率（只算事实，不判断是否"匹配"）
    if plan.amount > 0:
        amount_deviation = (trade_amount - plan.amount) / plan.amount
    else:
        amount_deviation = Decimal("0")

    # 格式化偏差说明
    deviation_pct = int(amount_deviation * 100)
    if deviation_pct == 0:
        amount_reason = f"金额: {trade_amount} (计划: {plan.amount})"
    elif deviation_pct > 0:
        amount_reason = f"金额: {trade_amount} (+{deviation_pct}%)"
    else:
        amount_reason = f"金额: {trade_amount} ({deviation_pct}%)"

    reason = f"{date_reason}; {amount_reason}"
    return date_match, amount_deviation, reason


@dependency
def build_dca_facts_for_batch(
    *,
    batch_id: int,
    fund_code: str | None = None,
    trade_repo: TradeRepo | None = None,
) -> list[FundDcaFacts]:
    """
    构建指定批次的 DCA 事实快照（只读，供 AI 分析使用）。

    规则层只输出事实，不做语义判断。返回的 FundDcaFacts 包含：
    - 交易日期序列、金额序列
    - 间隔天数分布
    - 金额直方图

    Args:
        batch_id: 导入批次 ID。
        fund_code: 可选的基金代码过滤。
        trade_repo: 交易仓储。

    Returns:
        按基金分组的事实快照列表。
    """
    log(f"[DcaFacts] 构建批次 {batch_id} 的事实快照...")

    # 1. 查询批次交易（只处理 buy）
    all_trades = trade_repo.list_by_batch(batch_id, fund_code)
    buy_trades = [t for t in all_trades if t.type == "buy"]

    if not buy_trades:
        log(f"[DcaFacts] 批次 {batch_id} 没有买入交易")
        return []

    # 2. 按基金分组
    trades_by_fund: dict[str, list] = defaultdict(list)
    for trade in buy_trades:
        trades_by_fund[trade.fund_code].append(trade)

    # 3. 构建每只基金的事实快照
    results: list[FundDcaFacts] = []
    for code, trades in sorted(trades_by_fund.items()):
        # 按日期排序
        sorted_trades = sorted(trades, key=lambda t: t.trade_date)
        dates = [t.trade_date for t in sorted_trades]
        amounts = [t.amount for t in sorted_trades]

        # 金额分布 + 众数
        amount_hist: dict[str, int] = defaultdict(int)
        for amt in amounts:
            amount_hist[str(amt)] += 1
        mode_amount = Decimal(max(amount_hist, key=amount_hist.get)) if amount_hist else None

        # 间隔分布 + 众数
        interval_hist: dict[int, int] = defaultdict(int)
        intervals: list[int] = []
        for i in range(1, len(dates)):
            delta = (dates[i] - dates[i - 1]).days
            interval_hist[delta] += 1
            intervals.append(delta)
        mode_interval = max(interval_hist, key=interval_hist.get) if interval_hist else 1

        # 最近稳定值（从末尾向前找连续相同金额）
        stable_amount = amounts[-1] if amounts else None
        stable_count = 1
        stable_since = dates[-1] if dates else None
        for i in range(len(amounts) - 2, -1, -1):
            if amounts[i] == stable_amount:
                stable_count += 1
                stable_since = dates[i]
            else:
                break

        # 识别特殊交易（优化：只标记显著变化）
        flags: list[TradeFlag] = []
        
        # 1. 金额显著变化（>15%）
        flags.extend(_identify_amount_changes(sorted_trades, threshold=Decimal("0.15"), max_flags=20))
        
        # 2. 金额异常（偏离众数 >50%）
        flags.extend(_identify_amount_outliers(sorted_trades, mode_amount))
        
        # 3. 间隔异常（超过众数 3 倍）
        flags.extend(_identify_interval_outliers(sorted_trades, intervals, mode_interval))

        results.append(
            FundDcaFacts(
                fund_code=code,
                batch_id=batch_id,
                trade_count=len(sorted_trades),
                first_date=dates[0] if dates else None,
                last_date=dates[-1] if dates else None,
                mode_amount=mode_amount,
                stable_amount=stable_amount,
                stable_since=stable_since,
                stable_count=stable_count,
                amount_histogram=dict(amount_hist),
                mode_interval=mode_interval,
                interval_histogram=dict(interval_hist),
                flags=flags,
            )
        )

    log(f"[DcaFacts] 生成 {len(results)} 只基金的事实快照")
    return results


def _identify_amount_changes(
    sorted_trades: list,
    threshold: Decimal = Decimal("0.15"),
    max_flags: int = 20,
) -> list[TradeFlag]:
    """
    识别显著金额变化点（只标记 >threshold 的变化）。

    Args:
        sorted_trades: 按日期排序的交易列表。
        threshold: 变化阈值（默认 15%）。
        max_flags: 最多返回多少个标记。

    Returns:
        变化点标记列表。
    """
    flags: list[TradeFlag] = []
    prev_amount: Decimal | None = None

    for trade in sorted_trades:
        amt = trade.amount

        if prev_amount is not None and prev_amount > 0:
            change_rate = abs(amt - prev_amount) / prev_amount

            # 只标记显著变化
            if change_rate > threshold:
                pct = int(((amt - prev_amount) / prev_amount) * 100)
                sign = "+" if pct > 0 else ""

                flags.append(
                    TradeFlag(
                        trade_id=trade.id,
                        trade_date=trade.trade_date,
                        amount=amt,
                        flag_type="amount_change",
                        detail=f"金额显著变化: {prev_amount}→{amt} ({sign}{pct}%)",
                    )
                )

        prev_amount = amt

    # 限制数量（避免 token 爆炸）
    return flags[:max_flags]


def _identify_amount_outliers(
    sorted_trades: list,
    mode_amount: Decimal | None,
) -> list[TradeFlag]:
    """识别金额异常（偏离众数 >50%）。"""
    if not mode_amount or mode_amount == 0:
        return []

    flags: list[TradeFlag] = []
    for trade in sorted_trades:
        deviation = abs(trade.amount - mode_amount) / mode_amount
        if deviation > Decimal("0.5"):
            pct = int(((trade.amount - mode_amount) / mode_amount) * 100)
            sign = "+" if pct > 0 else ""
            flags.append(
                TradeFlag(
                    trade_id=trade.id,
                    trade_date=trade.trade_date,
                    amount=trade.amount,
                    flag_type="amount_outlier",
                    detail=f"金额异常: 众数{mode_amount}元，偏离{sign}{pct}%",
                )
            )
    return flags


def _identify_interval_outliers(
    sorted_trades: list,
    intervals: list[int],
    mode_interval: int,
) -> list[TradeFlag]:
    """识别间隔异常（超过众数 3 倍）。"""
    if not intervals or mode_interval == 0:
        return []

    flags: list[TradeFlag] = []
    for i, trade in enumerate(sorted_trades[1:], start=1):
        if intervals[i - 1] > mode_interval * 3:
            flags.append(
                TradeFlag(
                    trade_id=trade.id,
                    trade_date=trade.trade_date,
                    amount=trade.amount,
                    flag_type="interval_outlier",
                    detail=f"间隔异常: {intervals[i - 1]}天，正常{mode_interval}天",
                )
            )
    return flags
