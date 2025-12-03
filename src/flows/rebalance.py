"""再平衡建议业务流程。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

from src.core.dependency import dependency
from src.core.models import AssetClass, NavQuality
from src.core.rules.rebalance import (
    FundSuggestion,
    RebalanceAdvice,
    build_rebalance_advice,
)
from src.data.client.local_nav import LocalNavService
from src.data.db.alloc_config_repo import AllocConfigRepo
from src.data.db.calendar import CalendarService
from src.data.db.fund_repo import FundRepo
from src.data.db.trade_repo import TradeRepo


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
    # 1. 确定目标日期
    if today is None:
        prev_day = calendar_service.prev_open("CN_A", date.today(), lookback=15)
        if prev_day is None:
            raise RuntimeError("未能找到上一交易日（15天内），请检查 trading_calendar 表数据")
        today = prev_day

    # 2. 获取配置和持仓数据
    target_weights = alloc_config_repo.get_target_weights()
    thresholds = alloc_config_repo.get_max_deviation()
    position_shares = trade_repo.get_position()

    # 3. 聚合当日市值（使用 NAV 质量分级逻辑）
    class_values: dict[AssetClass, Decimal] = {}
    nav_quality_summary: dict[str, NavQuality] = {}
    skipped_funds: list[str] = []

    # 需要从 report.py 导入 _get_nav_with_quality
    from src.flows.report import _get_nav_with_quality

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

    # 4. 计算实际权重
    actual_weight: dict[AssetClass, Decimal] = {}
    if total_value > Decimal("0"):
        for asset_class, value in class_values.items():
            actual_weight[asset_class] = value / total_value

    if total_value == Decimal("0"):
        return RebalanceResult(
            as_of=today,
            total_value=total_value,
            suggestions=[],
            no_market_data=True,
            note="当日 NAV 缺失，无法给出金额建议",
        )

    # 5. 生成资产类别级别建议
    suggestions = build_rebalance_advice(
        total_value=total_value,
        actual_weight=actual_weight,
        target_weight=target_weights,
        thresholds=thresholds,
        default_threshold=Decimal("0.05"),
    )

    # 6. 生成基金级别建议
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
    # 需要从 report.py 导入 _get_nav_with_quality
    from src.flows.report import _get_nav_with_quality

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
