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
    BackfillDaysResult,
    DcaDayCheck,
    FundDcaFacts,
    SkippedTrade,
    TradeFlag,
)
from src.data.db.action_repo import ActionRepo
from src.data.db.trade_repo import TradeRepo


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


# ============ AI 驱动的回填接口（v0.4.5 新增）============


def _check_date_on_track(
    trade_date: date,
    track_freq: str,
    track_rule: str,
) -> bool:
    """
    检查日期是否在定投轨道上。

    Args:
        trade_date: 交易日期。
        track_freq: 定投频率（daily / weekly / monthly）。
        track_rule: 定投规则（weekly 时为 MON-SUN，monthly 时为 1-31）。

    Returns:
        是否在轨道上。
    """
    if track_freq == "daily":
        return True

    if track_freq == "weekly":
        weekday_map = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
        actual = weekday_map[trade_date.weekday()]
        return actual == track_rule

    if track_freq == "monthly":
        expected_day = int(track_rule)
        actual_day = trade_date.day
        # 处理短月：31号计划在30天月份也能匹配月末
        if expected_day > 28:
            next_month = trade_date.replace(day=28) + timedelta(days=4)
            last_day = (next_month.replace(day=1) - timedelta(days=1)).day
            return actual_day == expected_day or (
                actual_day == last_day and expected_day > last_day
            )
        return actual_day == expected_day

    return False


@dependency
def get_dca_day_checks(
    *,
    batch_id: int,
    fund_code: str,
    track_freq: str,
    track_rule: str,
    trade_repo: TradeRepo | None = None,
) -> list[DcaDayCheck]:
    """
    获取每天的 DCA 轨道检查结果（规则层，只读）。

    用于 AI 驱动的回填流程：
    - AI 指定轨道参数（track_freq, track_rule）
    - 规则层返回每天的检查结果
    - AI 基于结果决定如何回填

    Args:
        batch_id: 导入批次 ID。
        fund_code: 基金代码。
        track_freq: 定投频率（daily / weekly / monthly）。
        track_rule: 定投规则。
        trade_repo: 交易仓储。

    Returns:
        按日期排序的 DcaDayCheck 列表。
    """
    # 1. 查询批次交易（只处理 buy）
    all_trades = trade_repo.list_by_batch(batch_id, fund_code)
    buy_trades = [t for t in all_trades if t.type == "buy"]

    if not buy_trades:
        return []

    # 2. 按日期分组
    trades_by_date: dict[date, list] = defaultdict(list)
    for trade in buy_trades:
        trades_by_date[trade.trade_date].append(trade)

    # 3. 对每一天生成检查结果
    results: list[DcaDayCheck] = []
    for day, trades in sorted(trades_by_date.items()):
        is_on_track = _check_date_on_track(day, track_freq, track_rule)

        results.append(
            DcaDayCheck(
                date=day,
                is_on_track=is_on_track,
                trade_count=len(trades),
                trade_ids=[t.id for t in trades],
                amounts=[t.amount for t in trades],
            )
        )

    return results


@dependency
def backfill_days(
    *,
    trade_ids: list[int],
    dca_plan_key: str,
    valid_amounts: list[Decimal] | None = None,
    trade_repo: TradeRepo | None = None,
    action_repo: ActionRepo | None = None,
) -> BackfillDaysResult:
    """
    批量回填指定交易为 DCA 核心（AI 调用，写库）。

    Args:
        trade_ids: 要回填的交易 ID 列表。
        dca_plan_key: DCA 计划标识（通常为 fund_code）。
        valid_amounts: AI 指定的有效金额列表（从 Facts 推断）。
                       None 表示不过滤金额，全部回填。
        trade_repo: 交易仓储。
        action_repo: 行为日志仓储。

    Returns:
        BackfillDaysResult：包含输入数、更新数、跳过的交易详情。
    """
    input_count = len(trade_ids)
    skipped_trades: list[SkippedTrade] = []

    if not trade_ids:
        return BackfillDaysResult(input_count=0, updated_count=0)

    # 1. 获取所有交易详情
    trades = trade_repo.list_by_ids(trade_ids)
    trade_map = {t.id: t for t in trades}

    # 2. 如果指定了有效金额，过滤并记录跳过的
    if valid_amounts is not None:
        valid_set = set(valid_amounts)
        filtered_ids: list[int] = []

        for tid in trade_ids:
            trade = trade_map.get(tid)
            if trade is None:
                continue
            if trade.amount in valid_set:
                filtered_ids.append(tid)
            else:
                skipped_trades.append(
                    SkippedTrade(
                        trade_id=tid,
                        fund_code=trade.fund_code,
                        trade_date=trade.trade_date,
                        amount=trade.amount,
                        reason=f"金额 {trade.amount} 不在有效集合 {list(valid_amounts)} 内",
                    )
                )

        if skipped_trades:
            log(f"[Backfill] 金额过滤：跳过 {len(skipped_trades)} 笔")
        trade_ids = filtered_ids

    if not trade_ids:
        log("[Backfill] 过滤后无可回填交易")
        return BackfillDaysResult(
            input_count=input_count,
            updated_count=0,
            skipped_trades=skipped_trades,
        )

    # 3. 更新 trades.dca_plan_key
    updated = trade_repo.update_dca_plan_key_bulk(trade_ids, dca_plan_key)
    log(f"[Backfill] 更新 {updated} 笔交易的 dca_plan_key")

    # 4. 更新 action_log.strategy
    if action_repo is not None:
        action_updated = action_repo.update_strategy_by_trade_ids(trade_ids, "dca")
        log(f"[Backfill] 更新 {action_updated} 条 action_log 的 strategy")

    return BackfillDaysResult(
        input_count=input_count,
        updated_count=updated,
        skipped_trades=skipped_trades,
    )


@dependency
def set_dca_core(
    *,
    trade_id: int,
    dca_plan_key: str,
    trade_repo: TradeRepo | None = None,
    action_repo: ActionRepo | None = None,
) -> bool:
    """
    设置某笔交易为当天的 DCA 核心（AI 调用，写库）。

    约束：自动取消同一天同基金其他交易的 dca_plan_key。

    Args:
        trade_id: 交易 ID。
        dca_plan_key: DCA 计划标识。
        trade_repo: 交易仓储。
        action_repo: 行为日志仓储。

    Returns:
        是否成功。
    """
    # 1. 获取交易信息
    trade = trade_repo.get(trade_id)
    if trade is None:
        log(f"[Backfill] 交易 {trade_id} 不存在")
        return False

    # 2. 取消同一天同基金其他交易的 dca_plan_key
    same_day_ids = trade_repo.list_ids_by_fund_and_date(
        trade.fund_code, trade.trade_date
    )
    other_ids = [tid for tid in same_day_ids if tid != trade_id]
    if other_ids:
        trade_repo.update_dca_plan_key_bulk(other_ids, None)
        log(f"[Backfill] 取消同日 {len(other_ids)} 笔交易的 dca_plan_key")

    # 3. 设置当前交易为核心
    trade_repo.update_dca_plan_key_bulk([trade_id], dca_plan_key)
    log(f"[Backfill] 设置交易 {trade_id} 为 DCA 核心")

    # 4. 更新 action_log
    if action_repo is not None:
        action_repo.update_strategy_by_trade_ids([trade_id], "dca")

    return True
