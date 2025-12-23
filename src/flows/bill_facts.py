"""账单事实构建。

用途：
- build_bill_facts(): 从 BillItems 构建 BillFacts
- build_bill_summary(): 构建多基金汇总

设计原则：
- 只输出事实，不做推断
- 控制体量，避免爆 token
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from src.core.models.bill import (
    AmountPhase,
    Anomaly,
    BillFacts,
    BillItem,
    BillParseError,
    BillSummary,
)

# ============ 常量 ============

MAX_PHASES = 10  # 每只基金最多阶段数
PHASE_CHANGE_THRESHOLD = Decimal("0.1")  # 金额变化 >10% 视为新阶段

# 间隔桶配置
GAP_BUCKETS = ["1", "2-3", "4-6", "7", "8-14", "15-29", "30", ">30"]

MAX_GAP_ANOMALIES = 2  # gap 异常最多采样数
GAP_THRESHOLD = 30  # 间隔 >30 天视为 gap


# ============ Facts 构建 ============


def build_bill_facts(items: list[BillItem]) -> list[BillFacts]:
    """从 BillItems 构建 BillFacts（按基金分组）。

    Args:
        items: 解析后的账单记录列表

    Returns:
        各基金的事实快照列表
    """
    if not items:
        return []

    # 按基金代码分组
    by_fund: dict[str, list[BillItem]] = defaultdict(list)
    for item in items:
        by_fund[item.fund_code].append(item)

    results: list[BillFacts] = []

    for code, fund_items in sorted(by_fund.items()):
        # 按确认日期排序
        sorted_items = sorted(fund_items, key=lambda x: x.confirm_date)

        # 基本信息
        name = sorted_items[0].fund_name

        # 交易类型统计
        dca_count = sum(1 for x in sorted_items if x.trade_type == "dca_buy")
        normal_count = sum(1 for x in sorted_items if x.trade_type == "normal_buy")

        # 时间范围
        first = sorted_items[0].confirm_date
        last = sorted_items[-1].confirm_date

        # 金额阶段
        phases = _build_phases(sorted_items)

        # 间隔分布
        gaps = _build_gaps(sorted_items)

        # 周期分布
        weekdays = _build_weekdays(sorted_items)

        # 费用汇总
        total_fee = sum((x.fee for x in sorted_items), Decimal("0"))
        total_apply = sum((x.apply_amount for x in sorted_items), Decimal("0"))
        total_confirm = sum((x.confirm_amount for x in sorted_items), Decimal("0"))

        # 异常检测（只检测 gap，金额变化由 phases 表达）
        anomalies, anomaly_total = _build_anomalies(sorted_items)

        results.append(
            BillFacts(
                code=code,
                name=name,
                dca_count=dca_count,
                normal_count=normal_count,
                first=first,
                last=last,
                phases=phases,
                gaps=gaps,
                weekdays=weekdays,
                total_fee=total_fee,
                total_apply=total_apply,
                total_confirm=total_confirm,
                anomalies=anomalies,
                anomaly_total=anomaly_total,
            )
        )

    return results


def build_bill_summary(
    items: list[BillItem],
    errors: list[BillParseError],
) -> BillSummary:
    """构建账单汇总。

    Args:
        items: 解析后的账单记录列表
        errors: 解析错误列表

    Returns:
        账单汇总
    """
    facts = build_bill_facts(items)

    # 汇总统计
    total_funds = len(facts)
    total_trades = len(items)
    total_dca = sum(f.dca_count for f in facts)
    total_normal = sum(f.normal_count for f in facts)

    # 时间范围（跨所有基金）
    if items:
        first = min(x.confirm_date for x in items)
        last = max(x.confirm_date for x in items)
    else:
        first = None
        last = None

    # 费用汇总
    total_fee = sum((f.total_fee for f in facts), Decimal("0"))
    total_apply = sum((f.total_apply for f in facts), Decimal("0"))
    total_confirm = sum((f.total_confirm for f in facts), Decimal("0"))

    return BillSummary(
        total_funds=total_funds,
        total_trades=total_trades,
        total_dca=total_dca,
        total_normal=total_normal,
        first=first,
        last=last,
        total_fee=total_fee,
        total_apply=total_apply,
        total_confirm=total_confirm,
        facts=facts,
        errors=errors,
    )


# ============ 阶段构建 ============


@dataclass
class _DayGroup:
    """按天聚合的中间结构。"""

    day: date
    items: list[BillItem]
    unique_amounts: set[Decimal]

    @property
    def is_mixed(self) -> bool:
        """同一天是否有多种不同金额。"""
        return len(self.unique_amounts) > 1

    @property
    def representative_amt(self) -> Decimal:
        """代表金额（众数）。"""
        amounts = [x.apply_amount for x in self.items]
        return _mode(amounts) or amounts[0]


def _group_by_day(items: list[BillItem]) -> list[_DayGroup]:
    """按天聚合。"""
    by_day: dict[date, list[BillItem]] = defaultdict(list)
    for item in items:
        by_day[item.confirm_date].append(item)

    groups = []
    for day in sorted(by_day.keys()):
        day_items = by_day[day]
        unique_amounts = {x.apply_amount for x in day_items}
        groups.append(_DayGroup(day=day, items=day_items, unique_amounts=unique_amounts))

    return groups


def _build_phases(items: list[BillItem]) -> list[AmountPhase]:
    """构建金额阶段（按变化点切分）。

    策略：
    1. 先按天聚合
    2. 同一天多笔不同金额 → 单独成一个阶段（amounts 列出所有金额）
    3. 其他天按金额变化 >10% 切分阶段
    """
    if not items:
        return []

    day_groups = _group_by_day(items)

    if len(day_groups) == 1:
        # 只有一天
        group = day_groups[0]
        return [_finalize_day_group(group)]

    phases: list[AmountPhase] = []
    current_groups: list[_DayGroup] = []

    for group in day_groups:
        # 同一天多笔不同金额 → 单独成一个阶段
        if group.is_mixed:
            # 先结束当前累积的阶段
            if current_groups:
                phases.append(_finalize_groups(current_groups))
                current_groups = []
            # 这一天单独成阶段
            phases.append(_finalize_day_group(group))
            continue

        # 正常天：判断是否需要切换阶段
        if not current_groups:
            current_groups = [group]
            continue

        # 计算当前阶段的众数金额
        all_items = [item for g in current_groups for item in g.items]
        phase_mode = _mode([x.apply_amount for x in all_items])

        if phase_mode and phase_mode > 0:
            change_ratio = abs((group.representative_amt - phase_mode) / phase_mode)
            if change_ratio > PHASE_CHANGE_THRESHOLD:
                # 金额变化超过阈值，结束当前阶段
                phases.append(_finalize_groups(current_groups))
                current_groups = [group]
            else:
                current_groups.append(group)
        else:
            current_groups.append(group)

    # 处理最后累积的阶段
    if current_groups:
        phases.append(_finalize_groups(current_groups))

    # 限制数量
    return phases[:MAX_PHASES]


def _finalize_day_group(group: _DayGroup) -> AmountPhase:
    """将单天聚合转换为 AmountPhase。"""
    items = group.items
    fee = sum((x.fee for x in items), Decimal("0"))

    if group.is_mixed:
        # 同一天多笔不同金额
        amounts = sorted(group.unique_amounts)
        apply_amt = _mode([x.apply_amount for x in items]) or items[0].apply_amount
        confirm_amt = _mode([x.confirm_amount for x in items]) or items[0].confirm_amount
        return AmountPhase(
            start=group.day,
            end=group.day,
            apply_amt=apply_amt,
            confirm_amt=confirm_amt,
            count=len(items),
            fee=fee,
            amounts=amounts,
        )
    else:
        # 正常单一金额
        return AmountPhase(
            start=group.day,
            end=group.day,
            apply_amt=items[0].apply_amount,
            confirm_amt=items[0].confirm_amount,
            count=len(items),
            fee=fee,
        )


def _finalize_groups(groups: list[_DayGroup]) -> AmountPhase:
    """将多天聚合转换为 AmountPhase。"""
    all_items = [item for g in groups for item in g.items]

    # 众数金额
    apply_amt = _mode([x.apply_amount for x in all_items]) or all_items[0].apply_amount
    confirm_amt = _mode([x.confirm_amount for x in all_items]) or all_items[0].confirm_amount

    # 总手续费
    fee = sum((x.fee for x in all_items), Decimal("0"))

    return AmountPhase(
        start=groups[0].day,
        end=groups[-1].day,
        apply_amt=apply_amt,
        confirm_amt=confirm_amt,
        count=len(all_items),
        fee=fee,
    )


# ============ 间隔分布 ============


def _build_gaps(items: list[BillItem]) -> dict[str, int]:
    """构建间隔桶化。"""
    if len(items) < 2:
        return {}

    dates = [x.confirm_date for x in items]
    intervals = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]

    buckets: dict[str, int] = {b: 0 for b in GAP_BUCKETS}

    for gap in intervals:
        if gap == 1:
            buckets["1"] += 1
        elif 2 <= gap <= 3:
            buckets["2-3"] += 1
        elif 4 <= gap <= 6:
            buckets["4-6"] += 1
        elif gap == 7:
            buckets["7"] += 1
        elif 8 <= gap <= 14:
            buckets["8-14"] += 1
        elif 15 <= gap <= 29:
            buckets["15-29"] += 1
        elif gap == 30:
            buckets["30"] += 1
        else:
            buckets[">30"] += 1

    # 删除 0 值
    return {k: v for k, v in buckets.items() if v > 0}


# ============ 周期分布 ============


def _build_weekdays(items: list[BillItem]) -> dict[str, int]:
    """构建星期分布。"""
    labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    counter: Counter[str] = Counter(labels[x.confirm_date.weekday()] for x in items)
    return dict(counter.most_common())


# ============ 异常检测 ============


def _build_anomalies(items: list[BillItem]) -> tuple[list[Anomaly], int]:
    """识别异常交易（限量采样）。

    设计原则：
    - 金额变化已由 phases 压缩表达，不再检测 spike
    - 只检测 gap（间隔 >30 天），这是 phases 无法表达的

    kind:
    - gap: 长时间间隔（>30天）
    """
    all_anomalies: list[Anomaly] = []
    anomaly_id = 1

    # gap: 长时间间隔
    if len(items) >= 2:
        for i in range(1, len(items)):
            gap_days = (items[i].confirm_date - items[i - 1].confirm_date).days
            if gap_days > GAP_THRESHOLD:
                all_anomalies.append(
                    Anomaly(
                        id=anomaly_id,
                        kind="gap",
                        day=items[i].confirm_date,
                        values={"gap_days": str(gap_days)},
                        note=f"间隔{gap_days}天",
                    )
                )
                anomaly_id += 1

    total = len(all_anomalies)

    # 限量采样
    sampled = all_anomalies[:MAX_GAP_ANOMALIES]

    return sampled, total


# ============ 工具函数 ============


def _mode(items: list[Any]) -> Any | None:  # noqa: ANN401
    """计算众数。"""
    if not items:
        return None
    counter = Counter(items)
    return counter.most_common(1)[0][0]
