"""日报与再平衡相关业务流程。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

from src.core.dependency import dependency
from src.core.models.asset_class import AssetClass
from src.core.models.nav import NavQuality
from src.core.models.trade import Trade
from src.core.rules.rebalance import (
    FundSuggestion,
    RebalanceAdvice,
    build_rebalance_advice,
    calc_weight_diff,
)
from src.data.client.discord import DiscordReportService
from src.data.client.local_nav import LocalNavService
from src.data.db.alloc_config_repo import AllocConfigRepo
from src.data.db.calendar import CalendarService
from src.data.db.fund_repo import FundRepo
from src.data.db.trade_repo import TradeRepo

ReportMode = str  # "market" | "shares"


@dataclass(slots=True, frozen=True)
class NavResult:
    """
    NAV 查询结果（不可变）。

    - nav: 净值（可能为 None）
    - quality: 数据质量等级
    - actual_date: 实际使用的 NAV 日期（可能不是查询日期）
    """

    nav: Decimal | None
    quality: NavQuality
    actual_date: date | None


@dataclass(slots=True)
class ReportResult:
    """
    日报数据结构（支持市值视图与份额视图）。

    口径：
    - 仅统计"已确认份额"，不包含当日 pending 交易；
    - 市值模式仅使用"当日官方 NAV"，`nav <= 0` 视为缺失；
    - 缺失 NAV 的基金不计入市值与权重分母，并在 missing_nav 中列出；
    - 不做"最近交易日 NAV"回退（v0.2 严格版），因此当日总市值可能被低估。

    统计字段（仅在市值模式下有意义）：
    - total_funds_in_position：本次参与市值统计且在 fund_repo 中有配置的持仓基金数；
    - funds_with_nav：当日拿到有效 NAV（>0）的基金数量。
    """

    mode: ReportMode
    as_of: date
    total_value: Decimal
    class_value: dict[AssetClass, Decimal]
    class_weight: dict[AssetClass, Decimal]
    deviation: dict[AssetClass, Decimal]
    missing_nav: list[str]
    total_funds_in_position: int
    funds_with_nav: int


@dataclass(slots=True)
class RebalanceResult:
    """
    再平衡建议结果（含基金级别建议 + NAV 质量元数据）。

    - as_of: 建议生成日期（通常为今天）；
    - total_value: 参与建议计算的组合总市值；
    - suggestions: 按资产类别的建议列表，已按偏离绝对值降序排序；
    - fund_suggestions: 按资产类别分组的基金级别建议；
    - nav_quality_summary: 各基金 NAV 质量等级；
    - skipped_funds: 因 NAV 缺失而跳过的基金列表。
    """

    as_of: date
    total_value: Decimal
    suggestions: list[RebalanceAdvice]
    fund_suggestions: dict[AssetClass, list[FundSuggestion]] = field(default_factory=dict)
    nav_quality_summary: dict[str, NavQuality] = field(default_factory=dict)
    skipped_funds: list[str] = field(default_factory=list)
    no_market_data: bool = False
    note: str | None = None


@dependency
def make_daily_report(
    *,
    mode: ReportMode = "market",
    as_of: date | None = None,
    alloc_config_repo: AllocConfigRepo | None = None,
    trade_repo: TradeRepo | None = None,
    fund_repo: FundRepo | None = None,
    nav_service: LocalNavService | None = None,
    calendar_service: CalendarService | None = None,
) -> str:
    """
    生成文本日报（市值/份额两种模式）。

    业务口径：
    - 仅统计"已确认份额"，不包含当日 pending；
    - 市值模式按"确认为准的份额 × 当日官方 NAV"计算；`nav <= 0` 视为缺失并在文末列出；
    - 缺失 NAV 的基金不参与市值累计与权重分母；
    - 严格版不做 NAV 回退；
    - 再平衡提示阈值当前固定为 ±5%（后续可配置）。

    Args:
        mode: 视图模式，`market`（市值）或 `shares`（份额），默认 `market`。
        as_of: 展示日，None 时使用上一交易日。
        alloc_config_repo: 配置仓储（自动注入）。
        trade_repo: 交易仓储（自动注入）。
        fund_repo: 基金仓储（自动注入）。
        nav_service: 净值查询服务（自动注入）。
        calendar_service: 交易日历服务（自动注入）。

    Returns:
        文本格式的日报内容。

    Raises:
        RuntimeError: 日历数据缺失时。
    """
    # 所有依赖已通过装饰器自动注入

    # 默认使用上一交易日
    if as_of is None:
        prev_day = calendar_service.prev_open("CN_A", date.today(), lookback=15)
        if prev_day is None:
            raise RuntimeError("未能找到上一交易日（15天内），请检查 trading_calendar 表数据")
        as_of = prev_day

    target_weights = alloc_config_repo.get_target_weights()
    position_shares = trade_repo.position_shares()

    report_data = (
        _build_market_view(position_shares, target_weights, as_of, fund_repo, nav_service)
        if mode == "market"
        else _build_share_view(position_shares, target_weights, as_of, fund_repo)
    )

    # v0.2.1: 获取最近交易用于确认情况展示
    recent_trades = trade_repo.list_recent_trades(days=7)

    return _render_report(report_data, target_weights, recent_trades)


@dependency
def send_daily_report(
    *,
    mode: ReportMode = "market",
    as_of: date | None = None,
    discord_service: DiscordReportService | None = None,
) -> bool:
    """
    发送日报（默认市值模式）。

    Args:
        mode: 视图模式，`market` 或 `shares`。
        as_of: 展示日（通常为上一交易日）。
        discord_service: Discord 推送服务（可选，自动注入）。

    Returns:
        发送是否成功。
    """
    # discord_service 已通过装饰器自动注入
    report_text = make_daily_report(mode=mode, as_of=as_of)
    return discord_service.send(report_text)


@dependency
def make_rebalance_suggestion(
    *,
    today: date | None = None,
    alloc_config_repo: AllocConfigRepo | None = None,
    trade_repo: TradeRepo | None = None,
    fund_repo: FundRepo | None = None,
    nav_service: LocalNavService | None = None,
    calendar_service: CalendarService | None = None,
) -> RebalanceResult:
    """
    生成资产配置再平衡建议（含基金级别建议 + NAV 智能降级）。

    口径：
    - 权重口径与"市值版日报"一致：仅使用已确认份额；
    - NAV 策略：
      - 优先使用当日 NAV（exact）
      - 周末/节假日：降级使用最近交易日 NAV（holiday）
      - NAV 延迟 1-2 天：降级使用（delayed，带警告）
      - NAV 缺失 3+ 天：跳过该基金（missing）
    - 阈值来源优先使用 alloc_config.max_deviation；未配置时使用默认 5%；
    - 建议金额采用 calc_rebalance_amount（总市值 × |偏离| × 50%），仅用于提示。

    Args:
        today: 建议生成日期，None 时使用上一交易日。
        alloc_config_repo: 配置仓储（自动注入）。
        trade_repo: 交易仓储（自动注入）。
        fund_repo: 基金仓储（自动注入）。
        nav_service: 净值查询服务（自动注入）。
        calendar_service: 交易日历服务（自动注入）。

    Returns:
        再平衡建议结果（含基金建议 + NAV 质量元数据）。

    Raises:
        RuntimeError: 日历数据缺失时。
    """
    # 所有依赖已通过装饰器自动注入

    # 默认使用上一交易日
    if today is None:
        prev_day = calendar_service.prev_open("CN_A", date.today(), lookback=15)
        if prev_day is None:
            raise RuntimeError("未能找到上一交易日（15天内），请检查 trading_calendar 表数据")
        today = prev_day

    target_weights = alloc_config_repo.get_target_weights()
    thresholds = alloc_config_repo.get_max_deviation()
    position_shares = trade_repo.position_shares()

    # 聚合当日市值（使用 NAV 质量分级逻辑）
    class_values: dict[AssetClass, Decimal] = {}
    nav_quality_summary: dict[str, NavQuality] = {}
    skipped_funds: list[str] = []

    for fund_code, shares in position_shares.items():
        fund = fund_repo.get(fund_code)
        if not fund:
            continue

        nav_result = _get_nav_with_quality(fund_code, today, nav_service, calendar_service, fund.market)

        if nav_result.quality == NavQuality.missing or nav_result.nav is None:
            skipped_funds.append(fund_code)
            continue

        value = shares * nav_result.nav
        asset_class: AssetClass = fund.asset_class
        class_values[asset_class] = class_values.get(asset_class, Decimal("0")) + value
        nav_quality_summary[fund_code] = nav_result.quality

    total_value = sum(class_values.values(), Decimal("0"))

    # 计算实际权重
    actual_weight: dict[AssetClass, Decimal] = {}
    if total_value > Decimal("0"):
        for asset_class, value in class_values.items():
            actual_weight[asset_class] = value / total_value

    if total_value == Decimal("0"):
        # 特判：当日 NAV 数据不足，无法给出金额建议
        return RebalanceResult(
            as_of=today,
            total_value=total_value,
            suggestions=[],
            no_market_data=True,
            note="当日 NAV 缺失，无法给出金额建议",
        )

    suggestions = build_rebalance_advice(
        total_value=total_value,
        actual_weight=actual_weight,
        target_weight=target_weights,
        thresholds=thresholds,
        default_threshold=Decimal("0.05"),
    )

    # 生成基金级别建议（v0.3.3）
    fund_suggestions: dict[AssetClass, list[FundSuggestion]] = {}
    for advice in suggestions:
        if advice.action != "hold":
            fund_suggestions[advice.asset_class] = _suggest_specific_funds(
                asset_class=advice.asset_class,
                target_amount=advice.amount,
                action=advice.action,
                fund_repo=fund_repo,
                position_shares=position_shares,
                nav_service=nav_service,
                calendar_service=calendar_service,
                today=today,
            )

    return RebalanceResult(
        as_of=today,
        total_value=total_value,
        suggestions=suggestions,
        fund_suggestions=fund_suggestions,
        nav_quality_summary=nav_quality_summary,
        skipped_funds=skipped_funds,
    )


# ========== 私有辅助函数 ==========


def _build_market_view(
    position_shares: dict[str, Decimal],
    target_weights: dict[AssetClass, Decimal],
    as_of: date,
    fund_repo: FundRepo,
    nav_service: LocalNavService,
) -> ReportResult:
    """
    构造市值视图数据：按"确认为准的份额 × 当日 NAV"聚合市值与权重。

    规则（v0.2 严格版）：
    - 仅使用当日 NAV；`nav is None or nav <= 0` 视为缺失；
    - 缺失基金不计入市值与权重，代码记录在 missing_nav；
    - 额外统计参与基金数与当日有效 NAV 基金数，用于文案提示。
    """
    today = as_of
    class_values: dict[AssetClass, Decimal] = {}
    missing_nav: list[str] = []
    total_funds_in_position = 0
    funds_with_nav = 0

    for fund_code, shares in position_shares.items():
        fund = fund_repo.get(fund_code)
        if not fund:
            # 未配置基金：不计入分母，也不参与市值与缺失列表
            continue

        # 至此可确认该基金在 fund_repo 中有配置，计入分母
        total_funds_in_position += 1

        nav = nav_service.get_nav(fund_code, today)
        if nav is None or nav <= Decimal("0"):
            missing_nav.append(fund_code)
            continue

        value = shares * nav
        asset_class = fund.asset_class
        class_values[asset_class] = class_values.get(asset_class, Decimal("0")) + value
        funds_with_nav += 1

    total_value = sum(class_values.values(), Decimal("0"))
    class_weight: dict[AssetClass, Decimal] = {}
    if total_value > Decimal("0"):
        for asset_class, value in class_values.items():
            class_weight[asset_class] = value / total_value

    deviation = calc_weight_diff(class_weight, target_weights)

    return ReportResult(
        mode="market",
        as_of=today,
        total_value=total_value,
        class_value=class_values,
        class_weight=class_weight,
        deviation=deviation,
        missing_nav=missing_nav,
        total_funds_in_position=total_funds_in_position,
        funds_with_nav=funds_with_nav,
    )


def _build_share_view(
    position_shares: dict[str, Decimal],
    target_weights: dict[AssetClass, Decimal],
    as_of: date,
    fund_repo: FundRepo,
) -> ReportResult:
    """
    构造份额视图数据：按已确认份额聚合各资产类别份额并计算权重（不依赖 NAV）。
    """
    class_shares: dict[AssetClass, Decimal] = {}
    for fund_code, shares in position_shares.items():
        fund = fund_repo.get(fund_code)
        if not fund:
            continue
        asset_class = fund.asset_class
        class_shares[asset_class] = class_shares.get(asset_class, Decimal("0")) + shares

    total_shares = sum(class_shares.values(), Decimal("0"))
    class_weight: dict[AssetClass, Decimal] = {}
    if total_shares > Decimal("0"):
        for asset_class, shares in class_shares.items():
            class_weight[asset_class] = shares / total_shares

    deviation = calc_weight_diff(class_weight, target_weights)

    return ReportResult(
        mode="shares",
        as_of=as_of,
        total_value=total_shares,
        class_value=class_shares,
        class_weight=class_weight,
        deviation=deviation,
        missing_nav=[],
        total_funds_in_position=0,
        funds_with_nav=0,
    )


def _render_report(
    data: ReportResult, target: dict[AssetClass, Decimal], recent_trades: list[Trade]
) -> str:
    """
    将 ReportResult 渲染成文本格式（v0.2.1：新增交易确认情况）。

    说明：再平衡提示阈值当前固定为 ±5%（未读取配置）。
    """
    lines: list[str] = []

    mode_text = "市值" if data.mode == "market" else "份额"
    lines.append(f"【持仓日报 {data.as_of} | 模式：{mode_text}】\n")

    if data.mode == "market":
        lines.append(f"总市值：{data.total_value:.2f}\n")
    else:
        lines.append(f"总份额：{data.total_value:.2f}\n")

    lines.append("\n资产配置：\n")

    for asset_class in sorted(target.keys(), key=lambda x: x.value):
        actual_weight = data.class_weight.get(asset_class, Decimal("0"))
        target_weight = target[asset_class]
        dev = data.deviation.get(asset_class, Decimal("0"))

        actual_pct = actual_weight * 100
        target_pct = target_weight * 100
        dev_pct = dev * 100

        if dev > Decimal("0.05"):
            status = f"超配 +{dev_pct:.1f}%"
        elif dev < Decimal("-0.05"):
            status = f"低配 {dev_pct:.1f}%"
        else:
            status = "正常"

        lines.append(f"- {asset_class.value}：{actual_pct:.1f}% (目标 {target_pct:.1f}%，{status})\n")

    lines.append("\n⚠️ 再平衡提示：\n")
    has_rebalance_hint = False
    for asset_class, dev in data.deviation.items():
        if dev > Decimal("0.05"):
            lines.append(f"- {asset_class.value} 超配，建议减持\n")
            has_rebalance_hint = True
        elif dev < Decimal("-0.05"):
            lines.append(f"- {asset_class.value} 低配，建议增持\n")
            has_rebalance_hint = True

    if not has_rebalance_hint:
        lines.append("- 当前配置均衡，无需调整\n")

    # v0.2.1: 交易确认情况
    confirmation_section = _render_confirmation_status(recent_trades, data.as_of)
    if confirmation_section:
        lines.append(confirmation_section)

    if data.mode == "market" and data.missing_nav:
        # v0.2 严格版提示：当日 NAV 缺失会导致市值低估
        lines.append(
            f"\n提示：今日 {data.funds_with_nav}/{data.total_funds_in_position} 只基金有有效 NAV，总市值可能低估。\n"
        )
        lines.append("\nNAV 缺失（未计入市值）：\n")
        for code in data.missing_nav:
            lines.append(f"- {code}\n")

    return "".join(lines)


def _render_confirmation_status(trades: list[Trade], today: date) -> str:
    """
    生成交易确认情况板块（v0.3.2 优化版）。

    分三类：
    1. 已确认（正常）- 显示最近 5 笔
    2. 待确认（未到确认日）- 仅显示统计，不展开明细
    3. 异常延迟（已到确认日但 NAV 缺失）- 重点展示，加入操作建议
    """
    if not trades:
        return ""

    confirmed_trades = []
    waiting_trades = []
    delayed_trades = []

    for t in trades:
        if t.status == "confirmed":
            confirmed_trades.append(t)
        elif t.status == "pending":
            if t.confirmation_status == "delayed":
                delayed_trades.append(t)
            else:
                waiting_trades.append(t)

    lines = ["\n【交易确认情况】\n"]

    # 1. 已确认（最近 5 笔）
    if confirmed_trades:
        lines.append(f"\n✅ 已确认（最近 {min(5, len(confirmed_trades))} 笔）\n")
        for t in confirmed_trades[:5]:
            trade_type_text = "买入" if t.type == "buy" else "卖出"
            lines.append(
                f"  - {t.trade_date.strftime('%m-%d')} {trade_type_text} "
                f"{t.fund_code} {t.amount:.2f}元 "
                f"→ 已确认 {t.shares:.2f}份\n"
            )

    # 2. 待确认（仅统计，不展开明细）
    if waiting_trades:
        lines.append(f"\n💡 提示：当前有 {len(waiting_trades)} 笔交易待确认（正常进行中）\n")

    # 3. 异常延迟（重点展示 + 操作建议）
    if delayed_trades:
        lines.append(f"\n⚠️ 异常延迟（{len(delayed_trades)} 笔）—— 需要处理\n")
        for t in delayed_trades:
            trade_type_text = "买入" if t.type == "buy" else "卖出"
            delayed_days = (today - t.confirm_date).days if t.confirm_date else 0

            lines.append(f"  - {t.trade_date.strftime('%m-%d')} {trade_type_text} " f"{t.fund_code} {t.amount:.2f}元\n")
            if t.confirm_date:
                lines.append(f"    理论确认日：{t.confirm_date.strftime('%Y-%m-%d')}\n")
            lines.append(f"    当前状态：确认延迟（已超过 {delayed_days} 天）\n")
            lines.append(f"    延迟原因：{_get_delayed_reason_text(t.delayed_reason)}\n")
            lines.append(f"    建议操作：{_get_delayed_suggestion_command(t)}\n")

    return "".join(lines)


def _get_delayed_reason_text(reason: str | None) -> str:
    """延迟原因文案。"""
    if reason == "nav_missing":
        return "NAV 数据缺失（未获取到定价日官方净值）"
    return "原因未明"


def _get_delayed_suggestion_command(trade: Trade) -> str:
    """
    延迟交易的操作建议（v0.3.2 优化版）。

    返回具体的命令示例，让用户可以直接复制执行。
    """
    if trade.delayed_reason == "nav_missing" and trade.pricing_date:
        return f"python -m src.cli.fetch_navs --date {trade.pricing_date} --funds {trade.fund_code}"
    return "请检查数据源或手动补录 NAV"


def _get_nav_with_quality(
    fund_code: str,
    target_date: date,
    nav_service: LocalNavService,
    calendar: CalendarService,
    market: str = "CN_A",
) -> NavResult:
    """
    查询 NAV 并评估数据质量。

    逻辑：
    1. 尝试获取 target_date 的 NAV
    2. 如果成功 → exact
    3. 如果失败，检查 target_date 是否交易日：
       - 非交易日（周末/节假日）→ 查找最近交易日 → holiday
       - 交易日但 NAV 缺失 → 查找最近交易日 → delayed
       - 延迟 3+ 天或无可用 NAV → missing

    Args:
        fund_code: 基金代码。
        target_date: 目标日期。
        nav_service: NAV 查询服务。
        calendar: 交易日历服务。
        market: 市场标识（默认 "CN_A"）。

    Returns:
        NAV 查询结果（包含质量等级）。
    """
    # 1. 尝试获取当日 NAV
    nav = nav_service.get_nav(fund_code, target_date)
    if nav is not None and nav > Decimal("0"):
        return NavResult(nav, NavQuality.exact, target_date)

    # 2. 检查是否交易日
    try:
        is_trading_day = calendar.is_open(market, target_date)
    except RuntimeError:
        # 日历数据缺失，降级为 missing
        return NavResult(None, NavQuality.missing, None)

    # 3. 查找最近交易日的 NAV
    last_trading = calendar.prev_open(market, target_date)
    if last_trading is None:
        return NavResult(None, NavQuality.missing, None)

    fallback_nav = nav_service.get_nav(fund_code, last_trading)
    if fallback_nav is None or fallback_nav <= Decimal("0"):
        return NavResult(None, NavQuality.missing, None)

    # 4. 判断质量等级
    delay_days = (target_date - last_trading).days
    if not is_trading_day and delay_days <= 2:
        # 非交易日 + 2 天内 → 正常降级（周末/节假日）
        quality = NavQuality.holiday
    elif delay_days <= 2:
        # 交易日但 NAV 延迟 1-2 天 → 可接受降级
        quality = NavQuality.delayed
    else:
        # 延迟 3+ 天 → 数据质量太差，标记为 missing
        return NavResult(None, NavQuality.missing, None)

    return NavResult(fallback_nav, quality, last_trading)


def _suggest_specific_funds(
    asset_class: AssetClass,
    target_amount: Decimal,
    action: Literal["buy", "sell"],
    fund_repo: FundRepo,
    position_shares: dict[str, Decimal],
    nav_service: LocalNavService,
    calendar_service: CalendarService,
    today: date,
) -> list[FundSuggestion]:
    """
    将资产类别级别的建议拆分到具体基金。

    策略：
    - buy：优先推荐该类别下当前持仓较小的基金（平均化），包含无持仓基金；
    - sell：优先推荐持仓较大的基金（渐进式减仓），且金额不超过当前市值。

    NAV 策略：复用 _get_nav_with_quality() 智能降级逻辑。

    Returns:
        基金建议列表（按建议金额降序）。
    """
    # 1. 获取该资产类别下的所有基金
    all_funds = fund_repo.list_all()
    class_funds = [f for f in all_funds if f.asset_class == asset_class]

    if not class_funds:
        return []

    # 2. 计算每只基金的当前市值（使用智能降级 NAV）
    fund_values: dict[str, Decimal] = {}
    fund_navs: dict[str, Decimal] = {}  # 存储有效 NAV 用于买入建议

    for fund in class_funds:
        shares = position_shares.get(fund.fund_code, Decimal("0"))
        nav_result = _get_nav_with_quality(fund.fund_code, today, nav_service, calendar_service)

        if nav_result.nav is None or nav_result.nav <= Decimal("0"):
            continue

        fund_navs[fund.fund_code] = nav_result.nav

        if shares > Decimal("0"):
            fund_values[fund.fund_code] = shares * nav_result.nav
        elif action == "buy":
            # 买入时包含无持仓基金（市值为 0）
            fund_values[fund.fund_code] = Decimal("0")

    if not fund_values:
        return []

    total_class_value = sum(fund_values.values(), Decimal("0"))

    # 3. 按策略排序基金
    if action == "buy":
        # 买入：优先推荐持仓较小的基金（平均化）
        sorted_funds = sorted(fund_values.items(), key=lambda x: x[1])
    else:
        # 卖出：优先推荐持仓较大的基金，且排除无持仓基金
        sorted_funds = sorted(
            [(k, v) for k, v in fund_values.items() if v > Decimal("0")],
            key=lambda x: x[1],
            reverse=True,
        )

    if not sorted_funds:
        return []

    # 4. 分配金额到具体基金（简化策略：平均分配）
    suggestions: list[FundSuggestion] = []
    remaining = target_amount
    num_funds = len(sorted_funds)

    for i, (fund_code, current_value) in enumerate(sorted_funds):
        if remaining <= Decimal("0"):
            break

        fund = next(f for f in class_funds if f.fund_code == fund_code)
        current_pct = current_value / total_class_value if total_class_value > Decimal("0") else Decimal("0")

        # 简化：平均分配（或按当前占比分配）
        if i == num_funds - 1:
            # 最后一只基金：分配剩余全部金额
            allocated = remaining
        else:
            # 平均分配
            allocated = target_amount / Decimal(str(num_funds))
            allocated = min(allocated, remaining)

        # 卖出时限制金额不超过当前市值
        if action == "sell":
            allocated = min(allocated, current_value)

        suggestions.append(
            FundSuggestion(
                fund_code=fund_code,
                fund_name=fund.name,
                action=action,
                amount=allocated,
                current_value=current_value,
                current_pct=current_pct,
            )
        )

        remaining -= allocated

    # 按金额降序排序
    suggestions.sort(key=lambda x: x.amount, reverse=True)
    return suggestions
