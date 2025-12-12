"""DCA 回填与事实构建。

用途：
- build_facts(): 构建事实快照（给 AI/CLI）
- checks(): DCA 轨道检查
- backfill(): 回填 DCA 归属
- set_core(): 设置某天的 DCA 核心
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from src.core.dependency import dependency
from src.core.log import log
from src.core.models.dca_backfill import (
    Anomaly,
    BackfillResult,
    BatchSummary,
    Bucket,
    DayCheck,
    DcaFacts,
    Segment,
    Skipped,
)
from src.data.client.fund_data import FundDataClient
from src.data.db.action_repo import ActionRepo
from src.data.db.trade_repo import TradeRepo

# ============ 常量 ============

TOP_K = 3  # Top-K 金额
MAX_SEGMENTS = 10  # 每只基金最多输出段数
MAX_SAMPLES_PER_SEGMENT = 3  # 每段最多保留样本数
MAX_ANOMALIES_PER_KIND = 2  # 每种异常最多保留样本数

# 金额桶配置（元）
AMOUNT_BUCKETS_CONFIG = [
    (0, 200, "0-200"),
    (200, 800, "200-800"),
    (800, 1500, "800-1500"),
    (1500, float("inf"), ">1500"),
]

# 间隔桶配置
INTERVAL_BUCKETS = ["1", "2-3", "4-6", "7", "8-29", "30", ">30"]


# ============ Facts 构建 ============


@dependency
def build_facts(
    *,
    batch_id: int,
    fund_codes: list[str] | None = None,
    trade_repo: TradeRepo | None = None,
    fund_data_client: FundDataClient | None = None,
) -> list[DcaFacts]:
    """
    构建导入批次的事实快照。

    设计原则：
    - 只输出事实，不做推断
    - 控制体量，避免爆 token
    """
    log(f"[Facts] 构建批次 {batch_id} 的事实快照...")

    all_trades = trade_repo.list_by_batch(batch_id, None)
    if fund_codes:
        codes_set = set(fund_codes)
        all_trades = [t for t in all_trades if t.fund_code in codes_set]

    if not all_trades:
        log(f"[Facts] 批次 {batch_id} 没有交易记录")
        return []

    # 按基金分组
    by_fund: dict[str, list] = defaultdict(list)
    for t in all_trades:
        by_fund[t.fund_code].append(t)

    results: list[DcaFacts] = []

    for code, trades in sorted(by_fund.items()):
        sorted_trades = sorted(trades, key=lambda t: t.trade_date)
        buys = [t for t in sorted_trades if t.type == "buy"]
        sells = [t for t in sorted_trades if t.type == "sell"]

        if not buys:
            results.append(
                DcaFacts(
                    code=code,
                    batch=batch_id,
                    buys=0,
                    sells=len(sells),
                    first=sells[0].trade_date if sells else date.today(),
                    last=sells[-1].trade_date if sells else date.today(),
                    days=0,
                )
            )
            continue

        # 时间维度
        first = buys[0].trade_date
        last = buys[-1].trade_date
        days = (last - first).days

        # 全局模式
        amounts = [t.amount for t in buys]
        mode_amt = _mode(amounts)
        mode_gap = _mode_gap(buys)

        # 金额分布
        top_amts = _build_top_amounts(buys)
        buckets = _build_buckets(buys)

        # 间隔分布
        gaps = _build_gaps(buys)

        # 周期分布
        weekdays = _build_weekdays(buys)

        # 段（稳定片段）
        segments = _build_segments(buys)

        # 异常
        anomalies, anomaly_total = _build_anomalies(buys, mode_amt)

        # 查询限额（可选）
        limit = None
        if fund_data_client:
            try:
                parsed = fund_data_client.get_trading_restriction(code)
                if parsed and parsed.limit_amount:
                    limit = parsed.limit_amount
            except Exception:  # noqa: BLE001
                pass

        results.append(
            DcaFacts(
                code=code,
                batch=batch_id,
                buys=len(buys),
                sells=len(sells),
                first=first,
                last=last,
                days=days,
                mode_amt=mode_amt,
                mode_gap=mode_gap,
                top_amts=top_amts,
                buckets=buckets,
                gaps=gaps,
                weekdays=weekdays,
                segments=segments,
                anomalies=anomalies,
                anomaly_total=anomaly_total,
                limit=limit,
            )
        )

    log(f"[Facts] 生成 {len(results)} 只基金的事实快照")
    return results


def _build_top_amounts(buys: list) -> list[tuple[Decimal, int]]:
    """构建 Top-K 金额。"""
    counter: Counter[Decimal] = Counter(t.amount for t in buys)
    top = counter.most_common(TOP_K)
    return [(amt, cnt) for amt, cnt in top]


def _build_buckets(buys: list) -> list[Bucket]:
    """构建金额区间分布。"""
    total = len(buys)
    if total == 0:
        return []

    counts = [0] * len(AMOUNT_BUCKETS_CONFIG)

    for t in buys:
        amt = float(t.amount)
        for i, (low, high, _) in enumerate(AMOUNT_BUCKETS_CONFIG):
            if low <= amt < high:
                counts[i] += 1
                break

    buckets = []
    for i, (_, _, label) in enumerate(AMOUNT_BUCKETS_CONFIG):
        if counts[i] > 0:
            buckets.append(
                Bucket(
                    label=label,
                    count=counts[i],
                    pct=counts[i] / total,
                )
            )

    return buckets


def _build_gaps(buys: list) -> dict[str, int]:
    """构建间隔桶化。"""
    if len(buys) < 2:
        return {}

    dates = [t.trade_date for t in buys]
    intervals = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]

    buckets: dict[str, int] = {b: 0 for b in INTERVAL_BUCKETS}

    for gap in intervals:
        if gap == 1:
            buckets["1"] += 1
        elif 2 <= gap <= 3:
            buckets["2-3"] += 1
        elif 4 <= gap <= 6:
            buckets["4-6"] += 1
        elif gap == 7:
            buckets["7"] += 1
        elif 8 <= gap <= 29:
            buckets["8-29"] += 1
        elif gap == 30:
            buckets["30"] += 1
        else:
            buckets[">30"] += 1

    # 删除 0 值
    return {k: v for k, v in buckets.items() if v > 0}


def _build_weekdays(buys: list) -> dict[str, int]:
    """构建星期分布。"""
    labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    counter: Counter[str] = Counter(labels[t.trade_date.weekday()] for t in buys)
    return dict(counter.most_common())


def _build_segments(buys: list) -> list[Segment]:
    """
    构建稳定片段。

    简单策略：按金额变化切段（当金额与当前段众数偏离 >40% 时开始新段）。
    """
    if len(buys) < 3:  # 太少不切段
        return []

    segments: list[Segment] = []
    current_segment: list = []
    segment_id = 1

    for t in buys:
        if not current_segment:
            current_segment.append(t)
            continue

        # 计算当前段的众数金额
        seg_amounts = [x.amount for x in current_segment]
        seg_mode = _mode(seg_amounts)

        # 判断是否需要切段
        if seg_mode and seg_mode > 0:
            ratio = abs(float((t.amount - seg_mode) / seg_mode))
            if ratio > 0.4 and len(current_segment) >= 3:
                # 结束当前段，开始新段
                seg = _finalize_segment(segment_id, current_segment)
                segments.append(seg)
                segment_id += 1
                current_segment = [t]
            else:
                current_segment.append(t)
        else:
            current_segment.append(t)

    # 处理最后一段
    if len(current_segment) >= 3:
        seg = _finalize_segment(segment_id, current_segment)
        segments.append(seg)

    # 限制数量
    return segments[:MAX_SEGMENTS]


def _finalize_segment(seg_id: int, trades: list) -> Segment:
    """将一组交易转换为 Segment。"""
    dates = [t.trade_date for t in trades]
    amounts = [t.amount for t in trades]

    # 典型金额
    amount = _mode(amounts) or amounts[0]

    # 典型间隔
    if len(dates) >= 2:
        intervals = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
        gap = _mode(intervals) or intervals[0]
    else:
        gap = 0

    # 周期分布
    labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    counter: Counter[str] = Counter(labels[t.trade_date.weekday()] for t in trades)
    weekdays = dict(counter.most_common())

    # 采样（最多 3 条）
    samples = [(t.trade_date, t.amount) for t in trades[:MAX_SAMPLES_PER_SEGMENT]]

    return Segment(
        id=seg_id,
        start=dates[0],
        end=dates[-1],
        count=len(trades),
        amount=amount,
        gap=gap,
        weekdays=weekdays,
        samples=samples,
    )


def _build_anomalies(buys: list, mode_amt: Decimal | None) -> tuple[list[Anomaly], int]:
    """
    识别异常交易（限量采样）。

    kind:
    - spike: 大额突变（偏离众数 >50%）
    - multi: 同一天多笔交易
    - gap: 长时间间隔（>30天）
    """
    anomaly_groups: dict[tuple[date, str], list] = defaultdict(list)

    # 1. spike: 偏离众数
    if mode_amt and mode_amt > 0:
        for t in buys:
            ratio = float((t.amount - mode_amt) / mode_amt)
            if abs(ratio) > 0.5:
                anomaly_groups[(t.trade_date, "spike")].append(t)

    # 2. multi: 同一天多笔
    by_day: dict[date, list] = defaultdict(list)
    for t in buys:
        by_day[t.trade_date].append(t)

    for day, day_trades in by_day.items():
        if len(day_trades) > 1:
            anomaly_groups[(day, "multi")].extend(day_trades)

    # 3. gap: 长时间间隔
    if len(buys) >= 2:
        dates = [t.trade_date for t in buys]
        for i in range(1, len(dates)):
            gap_days = (dates[i] - dates[i - 1]).days
            if gap_days > 30:
                anomaly_groups[(dates[i], "gap")].append(buys[i])

    # 转换为 Anomaly 对象
    all_anomalies: list[Anomaly] = []
    group_id = 1

    for (day, kind), trades_in_group in sorted(anomaly_groups.items()):
        trade_ids = [t.id for t in trades_in_group]
        amounts = [t.amount for t in trades_in_group]

        # 生成 note
        if kind == "spike" and mode_amt:
            first_amt = amounts[0]
            ratio = float((first_amt - mode_amt) / mode_amt)
            note = f"{first_amt}元，众数{mode_amt}元，偏离{ratio:+.0%}"
        elif kind == "multi":
            note = f"当天{len(trades_in_group)}笔"
        elif kind == "gap":
            note = "间隔>30天"
        else:
            note = ""

        all_anomalies.append(
            Anomaly(
                id=group_id,
                kind=kind,
                day=day,
                trades=trade_ids,
                amounts=amounts,
                note=note,
            )
        )
        group_id += 1

    total = len(all_anomalies)

    # 限量：每种 kind 最多 N 条
    by_kind: dict[str, list[Anomaly]] = defaultdict(list)
    for a in all_anomalies:
        by_kind[a.kind].append(a)

    sampled: list[Anomaly] = []
    for kind in ["spike", "multi", "gap"]:
        sampled.extend(by_kind[kind][:MAX_ANOMALIES_PER_KIND])

    return sampled, total


def _mode(items: list) -> Any | None:  # noqa: ANN401
    """计算众数。"""
    if not items:
        return None
    counter = Counter(items)
    return counter.most_common(1)[0][0]


def _mode_gap(buys: list) -> int | None:
    """计算众数间隔。"""
    if len(buys) < 2:
        return None
    dates = [t.trade_date for t in buys]
    intervals = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
    return _mode(intervals)


# ============ 批次总览 ============


def summarize(facts_list: list[DcaFacts]) -> list[BatchSummary]:
    """将 DcaFacts 压缩成批次总览。"""
    summaries: list[BatchSummary] = []

    for f in facts_list:
        summaries.append(
            BatchSummary(
                code=f.code,
                buys=f.buys,
                start=f.first if f.buys > 0 else None,
                end=f.last if f.buys > 0 else None,
                mode_amt=f.mode_amt,
                anomaly_count=f.anomaly_total,
            )
        )

    return summaries


# ============ DCA 轨道检查 ============


def _is_on_track(day: date, freq: str, rule: str) -> bool:
    """判断某天是否在 DCA 轨道上。

    freq:
    - "daily": 工作日（Mon-Fri）
    - "weekly": 每周某天（rule = "MON" / "TUE" / ...）
    - "monthly": 每月某日（rule = "1" / "15" / ...）
    """
    if freq == "daily":
        return day.weekday() < 5  # Mon-Fri

    if freq == "weekly":
        if not rule:
            return False
        target_weekday = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}.get(
            rule.upper()
        )
        return target_weekday is not None and day.weekday() == target_weekday

    if freq == "monthly":
        if not rule:
            return False
        try:
            target_day = int(rule)
            return day.day == target_day
        except ValueError:
            return False

    return False


@dependency
def checks(
    *,
    batch_id: int,
    code: str,
    freq: str,
    rule: str,
    valid_amounts: list[Decimal],
    trade_repo: TradeRepo | None = None,
) -> list[DayCheck]:
    """
    检查批次内某基金的每天 DCA 轨道情况。

    Args:
        batch_id: 导入批次 ID
        code: 基金代码
        freq: 定投频率（daily/weekly/monthly）
        rule: 定投规则（weekly: "MON"/..., monthly: "1"/...）
        valid_amounts: 有效金额列表（用于过滤）
        trade_repo: 交易仓储（自动注入）

    Returns:
        每天的检查结果（on_track + 有效交易 ids/amounts）
    """
    trades = trade_repo.list_by_batch(batch_id, code)
    buys = [t for t in trades if t.type == "buy"]

    if not buys:
        return []

    # 按天分组
    by_day: dict[date, list] = defaultdict(list)
    for t in buys:
        by_day[t.trade_date].append(t)

    results: list[DayCheck] = []
    valid_set = set(valid_amounts)

    for day in sorted(by_day.keys()):
        day_trades = by_day[day]
        on_track = _is_on_track(day, freq, rule)

        # 过滤：只保留有效金额的交易
        valid_ids = [t.id for t in day_trades if t.amount in valid_set]
        valid_amounts_list = [t.amount for t in day_trades if t.amount in valid_set]

        results.append(
            DayCheck(
                day=day,
                on_track=on_track,
                count=len(valid_ids),
                ids=valid_ids,
                amounts=valid_amounts_list,
            )
        )

    return results


# ============ 回填 DCA 归属 ============


@dependency
def backfill(
    *,
    trade_ids: list[int],
    plan_key: str,
    valid_amounts: list[Decimal],
    trade_repo: TradeRepo | None = None,
    action_repo: ActionRepo | None = None,
) -> BackfillResult:
    """
    回填 DCA 归属。

    Args:
        trade_ids: 交易 ID 列表
        plan_key: 计划键（fund_code）
        valid_amounts: 有效金额列表（用于验证）
        trade_repo: 交易仓储（自动注入）
        action_repo: 行为日志仓储（自动注入）

    Returns:
        回填结果（total, updated, skipped）
    """
    if not trade_ids:
        return BackfillResult(total=0, updated=0)

    trades = trade_repo.list_by_ids(trade_ids)

    valid_set = set(valid_amounts)
    to_update: list[int] = []
    skipped: list[Skipped] = []

    for t in trades:
        if t.amount not in valid_set:
            skipped.append(
                Skipped(
                    id=t.id,
                    code=t.fund_code,
                    day=t.trade_date,
                    amount=t.amount,
                    reason=f"金额 {t.amount} 不在有效集合 {valid_amounts} 内",
                )
            )
        else:
            to_update.append(t.id)

    # 批量更新
    if to_update:
        action_repo.update_strategy_by_trade_ids(to_update, f"dca:{plan_key}")

    return BackfillResult(
        total=len(trades),
        updated=len(to_update),
        skipped=skipped,
    )


@dependency
def set_core(
    *,
    trade_id: int,
    plan_key: str,
    action_repo: ActionRepo | None = None,
) -> bool:
    """设置某笔交易为 DCA 核心。"""
    updated = action_repo.update_strategy_by_trade_ids([trade_id], f"dca_core:{plan_key}")
    return updated > 0
