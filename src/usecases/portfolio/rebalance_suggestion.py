from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional

from src.core.asset_class import AssetClass
from src.core.portfolio.rebalance import (
    RebalanceAdvice,
    build_rebalance_advice,
)
from src.core.protocols import AllocConfigRepo, FundRepo, NavProtocol, TradeRepo


@dataclass(slots=True)
class RebalanceSuggestionResult:
    """
    再平衡建议结果（基础版，仅资产类别粒度）。

    - as_of: 建议生成日期（通常为今天）；
    - total_value: 参与建议计算的组合总市值；
    - suggestions: 按资产类别的建议列表，已按偏离绝对值降序排序。
    """

    as_of: date
    total_value: Decimal
    suggestions: List[RebalanceAdvice]
    # 当日 NAV 全部缺失或 total_value==0 时标记为 True，并在 note 中给出提示
    no_market_data: bool = False
    note: Optional[str] = None


class MakeRebalance:
    """
    生成资产配置再平衡建议（基础版，仅文字提示，不自动下单）。

    口径：
    - 权重口径与"市值版日报"一致：仅使用已确认份额与当日 NAV（严格版，不回退）；
    - 阈值来源优先使用 alloc_config.max_deviation；未配置时使用默认 5%；
    - 建议金额采用 calc_rebalance_amount（总市值 × |偏离| × 50%），仅用于提示。
    """

    def __init__(
        self,
        alloc_repo: AllocConfigRepo,
        trade_repo: TradeRepo,
        fund_repo: FundRepo,
        nav_provider: NavProtocol,
    ) -> None:
        self.alloc_repo = alloc_repo
        self.trade_repo = trade_repo
        self.fund_repo = fund_repo
        self.nav_provider = nav_provider

    def execute(self, *, today: date) -> RebalanceSuggestionResult:
        """
        基于当日市值视图计算再平衡建议。

        步骤：
        1. 读取 target_weight 与 per-class max_deviation（若有）；
        2. 通过 TradeRepo.position_shares() 获取已确认持仓份额；
        3. 仅使用当日 NAV（nav<=0 视为缺失并剔除），聚合各资产类别市值与 total_value；
        4. 计算 actual_weight；
        5. 调用 build_rebalance_advice(total_value, actual_weight, target_weight, thresholds)；
        6. 返回 RebalanceSuggestionResult。
        """

        target_weights = self.alloc_repo.get_target_weights()
        thresholds = self.alloc_repo.get_max_deviation()

        position_shares = self.trade_repo.position_shares()

        # 聚合当日市值（严格口径：仅使用当日 NAV>0；未配置基金跳过）
        class_values: dict[AssetClass, Decimal] = {}
        for fund_code, shares in position_shares.items():
            fund = self.fund_repo.get_fund(fund_code)
            if not fund:
                continue
            nav = self.nav_provider.get_nav(fund_code, today)
            if nav is None or nav <= Decimal("0"):
                continue
            value = shares * nav
            asset_class: AssetClass = fund.asset_class
            class_values[asset_class] = class_values.get(asset_class, Decimal("0")) + value

        total_value = sum(class_values.values(), Decimal("0"))

        # 计算实际权重
        actual_weight: dict[AssetClass, Decimal] = {}
        if total_value > Decimal("0"):
            for asset_class, value in class_values.items():
                actual_weight[asset_class] = value / total_value

        if total_value == Decimal("0"):
            # 特判：当日 NAV 数据不足，无法给出金额建议
            return RebalanceSuggestionResult(
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

        return RebalanceSuggestionResult(
            as_of=today,
            total_value=total_value,
            suggestions=suggestions,
        )
