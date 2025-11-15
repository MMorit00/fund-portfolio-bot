from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Dict

from src.core.asset_class import AssetClass
from src.core.portfolio.rebalance import calc_weight_difference
from src.usecases.ports import AllocConfigRepo, FundRepo, ReportSender, TradeRepo


@dataclass
class ReportData:
    """
    日报数据结构。

    IMPORTANT: 当前版本基于份额计算，存在精度问题
    - total_value: 实际是总份额，不是总市值
    - class_value: 实际是各类别份额，不是市值
    - class_weight: 基于份额计算的权重，不是市值权重
    - ISSUE: 不同基金净值不同，份额不能准确反映真实价值配置

    TODO: 升级为市值计算 (见 roadmap.md 技术债部分)
    - 需要集成 NavProvider 获取最新净值
    - 市值 = 份额 × 最新净值
    - 权重 = 类别市值 / 总市值
    """
    total_value: Decimal  # 当前版本存储总份额，将来可改为总市值
    class_value: Dict[AssetClass, Decimal]  # 各资产类别的份额（将来可改为市值）
    class_weight: Dict[AssetClass, Decimal]  # 各资产类别的权重
    deviation: Dict[AssetClass, Decimal]  # 与目标权重的偏离


class GenerateDailyReport:
    """
    生成并发送日报（文本版）。

    当前版本（轻量版）：
    - 基于份额计算权重，不依赖 NAV
    - 显示总份额而非总市值
    - 计算与目标权重的偏离
    """

    def __init__(
        self,
        alloc_repo: AllocConfigRepo,
        trade_repo: TradeRepo,
        fund_repo: FundRepo,
        sender: ReportSender,
    ) -> None:
        self.alloc_repo = alloc_repo
        self.trade_repo = trade_repo
        self.fund_repo = fund_repo
        self.sender = sender

    def build(self) -> str:
        """构造日报文本内容。"""
        # 1. 获取持仓份额（fund_code -> shares）
        position_shares = self.trade_repo.position_shares()

        # 2. 按资产类别聚合份额
        class_shares: Dict[AssetClass, Decimal] = {}
        for fund_code, shares in position_shares.items():
            fund = self.fund_repo.get_fund(fund_code)
            if not fund:
                continue
            asset_class = fund["asset_class"]
            class_shares[asset_class] = class_shares.get(asset_class, Decimal("0")) + shares

        # 3. 计算总份额
        total_shares = sum(class_shares.values(), Decimal("0"))

        # 4. 计算各资产类别权重（归一化）
        class_weight: Dict[AssetClass, Decimal] = {}
        if total_shares > Decimal("0"):
            for asset_class, shares in class_shares.items():
                class_weight[asset_class] = shares / total_shares

        # 5. 获取目标权重
        target_weights = self.alloc_repo.get_target_weights()

        # 6. 计算偏离
        deviation = calc_weight_difference(class_weight, target_weights)

        # 7. 构造 ReportData
        report_data = ReportData(
            total_value=total_shares,  # 当前版本用总份额占位
            class_value=class_shares,
            class_weight=class_weight,
            deviation=deviation,
        )

        # 8. 渲染成文本
        return self._render(report_data, target_weights)

    def _render(self, data: ReportData, target: Dict[AssetClass, Decimal]) -> str:
        """将 ReportData 渲染成文本格式。"""
        today = date.today()
        lines = []

        lines.append(f"【持仓日报 {today}】\n")
        lines.append(f"总份额：{data.total_value:.2f}\n")
        lines.append("\n资产配置：\n")

        # 按资产类别输出（确保所有目标类别都显示）
        for asset_class in sorted(target.keys(), key=lambda x: x.value):
            actual_weight = data.class_weight.get(asset_class, Decimal("0"))
            target_weight = target[asset_class]
            dev = data.deviation.get(asset_class, Decimal("0"))

            # 格式化权重为百分比
            actual_pct = actual_weight * 100
            target_pct = target_weight * 100
            dev_pct = dev * 100

            # 判断状态
            if dev > Decimal("0.05"):  # 超配超过 5%
                status = f"超配 +{dev_pct:.1f}%"
            elif dev < Decimal("-0.05"):  # 低配超过 5%
                status = f"低配 {dev_pct:.1f}%"
            else:
                status = "正常"

            lines.append(
                f"- {asset_class.value}：{actual_pct:.1f}% (目标 {target_pct:.1f}%，{status})\n"
            )

        # 再平衡提示
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

        return "".join(lines)

    def send(self) -> bool:
        """发送日报。"""
        return self.sender.send(self.build())

