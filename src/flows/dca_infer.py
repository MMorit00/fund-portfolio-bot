"""从历史行为与交易记录推断定投计划（只读分析）。"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from typing import Iterable

from src.core.dependency import dependency
from src.core.models import DcaPlanDraft, MarketType
from src.data.db.action_repo import ActionRepo
from src.data.db.calendar import CalendarService
from src.data.db.trade_repo import TradeRepo


@dependency
def draft_dca_plans(
    *,
    min_samples: int = 6,
    min_span_days: int = 90,
    fund_code: str | None = None,
    action_repo: ActionRepo | None = None,
    trade_repo: TradeRepo | None = None,
    calendar_service: CalendarService | None = None,
) -> list[DcaPlanDraft]:
    """
    从历史行为推断定投计划草案（只读，不写库，符合 draft_*() 规范）。

    推断规则（简化实现，便于后续迭代）：

    1. 数据来源（from history）：
       - 从 ActionRepo 中读取 `action='buy'` 且 `source in ('manual', 'import')` 的行为日志；
       - 仅使用存在 `fund_code` 且 `trade_id` 非空的记录；
       - 通过 TradeRepo 按 trade_id 批量查询对应交易，获取 `amount` 和 `trade_date`。

    2. 分组与样本过滤：
       - 按 fund_code 分组买入记录，每组形成一条候选序列；
       - 组内按 trade_date 升序排序；
       - 计算样本数 `sample_count` 与时间跨度 `span_days`（首尾交易日差值）；
       - 若 `sample_count < min_samples` 或 `span_days < min_span_days`，则跳过该基金。

    3. 频率识别（daily/weekly/monthly）：
       - 计算相邻交易日之间的间隔列表 `diffs`；
       - 当存在交易日历（calendar_service 不为 None）时：
         * 使用“交易日数量”作为间隔单位：
           - 日度：`diff <= 1`
           - 周度：`4 <= diff <= 6`
           - 月度：`18 <= diff <= 25`
       - 当不存在交易日历时（回退模式）：
         * 使用自然日间隔判断节奏：
           - 日度：`diff <= 2`
           - 周度：`6 <= diff <= 8`
           - 月度：`28 <= diff <= 32`
       - 计算三类间隔占比，按以下优先级与阈值选择频率：
         * 日度：比例 >= 0.9 → daily
         * 周度：比例 >= 0.8 → weekly
         * 月度：比例 >= 0.8 → monthly
       - 若三类均不满足阈值，则视为无明显定投模式，跳过该基金。

    日历处理说明：
       - 优先使用 trading_calendar（通过 CalendarService）计算“交易日间隔”，
         长假（春节/国庆）对 daily/weekly 识别的影响更小；
       - 若 CalendarService 不可用或日历数据缺失，则自动回退为自然日差，
         该情况下长假仍可能降低 daily/weekly 模式的识别率（偏保守漏报）。

    4. 规则识别（rule）：
       - daily：rule 设为空字符串 `""`；
       - weekly：取样本中出现次数最多的星期几（MON/TUE/...）；
       - monthly：取样本中出现次数最多的日期（1..31）。

    5. 金额与置信度：
       - 金额 amount：取样本金额的中位数；
       - 置信度 confidence：
         * high: `sample_count >= 12` 且所选频率的间隔占比 >= 0.9
         * medium: `sample_count >= 6` 且间隔占比 >= 0.8
         * low: 其他情况（理论上已被 min_samples/min_span_days 剪枝，但保留作兜底）。

    返回：
        DcaPlanDraft 列表，每个元素对应一个 fund_code 的定投草案方案。
    """
    # 1. 读取行为日志并按基金过滤
    logs = action_repo.list_buy_actions(days=None)
    filtered_logs = [
        log
        for log in logs
        if log.fund_code
        and log.trade_id is not None
        and (fund_code is None or log.fund_code == fund_code)
    ]
    if not filtered_logs:
        return []

    # 2. 查询对应交易记录
    trade_ids = sorted({log.trade_id for log in filtered_logs if log.trade_id is not None})
    trades = trade_repo.list_by_ids(trade_ids)
    trades_by_id = {t.id: t for t in trades if t.id is not None}

    # 3. 按基金分组交易（只保留买入）
    trades_by_fund: dict[str, list[tuple[date, Decimal, MarketType]]] = defaultdict(list)
    for log in filtered_logs:
        trade = trades_by_id.get(log.trade_id or 0)
        if trade is None or trade.type != "buy":
            continue
        trades_by_fund[log.fund_code].append((trade.trade_date, trade.amount, trade.market))

    drafts: list[DcaPlanDraft] = []

    # 4. 对每只基金做节奏分析
    for code, items in trades_by_fund.items():
        if len(items) < 2:
            continue

        # 4.1 按日期排序，准备基础数据
        items.sort(key=lambda x: x[0])
        dates = [it[0] for it in items]
        amounts = [it[1] for it in items]
        market = items[0][2]
        sample_count = len(items)
        span_days = (dates[-1] - dates[0]).days

        # 样本数量与跨度过滤
        if sample_count < min_samples or span_days < min_span_days:
            continue

        diffs = _calc_day_diffs(
            dates,
            calendar_service=calendar_service,
            calendar_key=market.value if calendar_service is not None else None,
        )
        if not diffs:
            continue

        # 4.2 识别频率与间隔占比
        use_trading_days = calendar_service is not None
        freq, rule, ratio = _infer_frequency_and_rule(dates, diffs, use_trading_days)
        if freq is None or rule is None:
            continue

        # 4.3 计算金额中位数与置信度
        median_amount = _median_decimal(amounts)
        confidence = _infer_confidence(sample_count, ratio, freq)

        drafts.append(
            DcaPlanDraft(
                fund_code=code,
                amount=median_amount,
                frequency=freq,
                rule=rule,
                sample_count=sample_count,
                span_days=span_days,
                confidence=confidence,
                first_date=dates[0],
                last_date=dates[-1],
            )
        )

    return sorted(drafts, key=lambda d: (d.fund_code, d.frequency, d.rule))


def _calc_day_diffs(
    dates: list[date],
    *,
    calendar_service: CalendarService | None = None,
    calendar_key: str | None = None,
) -> list[int]:
    """
    计算相邻日期之间的间隔。

    - 当提供 calendar_service + calendar_key 时：
        使用“交易日数量”作为间隔单位（prev..curr 之间的开市天数）；
    - 否则：回退为自然日差。
    """
    if len(dates) < 2:
        return []

    # 回退模式：自然日差
    if calendar_service is None or calendar_key is None:
        return [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]

    # 交易日模式：统计 prev..curr 之间的开市日数量
    diffs: list[int] = []
    for i in range(1, len(dates)):
        start = dates[i - 1]
        end = dates[i]
        if end <= start:
            continue

        d = start
        trading_gap = 0
        while d < end:
            d = d + timedelta(days=1)
            try:
                if calendar_service.is_open(calendar_key, d):
                    trading_gap += 1
            except RuntimeError:
                # 日历缺失时降级为自然日差，避免推断直接失败
                trading_gap = (end - start).days
                break
        diffs.append(trading_gap)

    return diffs


def _count_intervals(diffs: Iterable[int], use_trading_days: bool) -> tuple[int, int, int, int]:
    """统计各类间隔数量：日度 / 周度 / 月度 / 总数。"""
    daily = weekly = monthly = 0
    total = 0
    for d in diffs:
        if d <= 0:
            continue
        total += 1
        if use_trading_days:
            # 交易日模式：daily≈1，weekly≈5，monthly≈20
            if d <= 1:
                daily += 1
            if 4 <= d <= 6:
                weekly += 1
            if 18 <= d <= 25:
                monthly += 1
        else:
            # 自然日模式：保留原有阈值
            if d <= 2:
                daily += 1
            if 6 <= d <= 8:
                weekly += 1
            if 28 <= d <= 32:
                monthly += 1
    return daily, weekly, monthly, total


def _infer_frequency_and_rule(
    dates: list[date],
    diffs: list[int],
    use_trading_days: bool,
) -> tuple[str | None, str | None, float]:
    """
    根据日期与间隔推断频率与规则。

    返回:
        (frequency, rule, ratio)
        - frequency: "daily"/"weekly"/"monthly" 或 None
        - rule: 对应规则字符串；无法识别时为 None
        - ratio: 选定频率下的“有效间隔占比”（0..1）
    """
    daily_count, weekly_count, monthly_count, total = _count_intervals(diffs, use_trading_days)
    if total == 0:
        return None, None, 0.0

    daily_ratio = daily_count / total
    weekly_ratio = weekly_count / total
    monthly_ratio = monthly_count / total

    # 1. 频率判定（先尝试日度，再周度，再月度）
    freq: str | None = None
    ratio = 0.0
    if daily_ratio >= 0.9:
        freq = "daily"
        ratio = daily_ratio
    elif weekly_ratio >= 0.8:
        freq = "weekly"
        ratio = weekly_ratio
    elif monthly_ratio >= 0.8:
        freq = "monthly"
        ratio = monthly_ratio
    else:
        return None, None, 0.0

    # 2. 规则推断
    if freq == "daily":
        rule = ""
    elif freq == "weekly":
        # 使用 weekday() + 固定映射，避免 %a 受本地化影响
        weekday_map = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
        weekdays = [weekday_map[d.weekday()] for d in dates]
        counter = Counter(weekdays)
        rule = counter.most_common(1)[0][0]
    else:  # monthly
        days = [d.day for d in dates]
        counter = Counter(days)
        rule = str(counter.most_common(1)[0][0])

    return freq, rule, ratio


def _median_decimal(values: list[Decimal]) -> Decimal:
    """计算 Decimal 列表的中位数。"""
    if not values:
        return Decimal("0")
    return median(values)  # type: ignore[return-value]


def _infer_confidence(sample_count: int, ratio: float, frequency: str) -> str:
    """根据样本数与间隔稳定性推断置信度。"""
    if sample_count >= 12 and ratio >= 0.9:
        return "high"
    if sample_count >= 6 and ratio >= 0.8:
        return "medium"
    return "low"
