from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Dict, List

from src.core.asset_class import AssetClass
from src.core.portfolio.rebalance import calc_weight_difference
from src.usecases.ports import AllocConfigRepo, FundRepo, NavProvider, ReportSender, TradeRepo


@dataclass
class ReportData:
    """
    日报数据结构（支持市值视图与份额视图）。

    口径：
    - 仅统计“已确认份额”，不包含当日 pending 交易；
    - 市值模式使用“当日官方 NAV”，`nav <= 0` 视为缺失；
    - 缺失 NAV 的基金不计入市值与权重分母，并在 missing_nav 中列出。
    """

    mode: str  # "market" 或 "shares"
    as_of: date
    total_value: Decimal
    class_value: Dict[AssetClass, Decimal]
    class_weight: Dict[AssetClass, Decimal]
    deviation: Dict[AssetClass, Decimal]
    missing_nav: List[str]


class GenerateDailyReport:
    """
    生成并发送文本日报（市值/份额两种模式）。

    业务口径：
    - 仅统计“已确认份额”，不包含当日 pending；
    - 市值模式按“确认为准的份额 × 当日官方 NAV”计算；`nav <= 0` 视为缺失并在文末列出；
    - 缺失 NAV 的基金不参与市值累计与权重分母；
    - 再平衡提示阈值当前固定为 ±5%（后续可配置）。

    模式：
    - market：市值视图（shares × NAV）
    - shares：份额视图（无 NAV 依赖）
    """

    def __init__(
        self,
        alloc_repo: AllocConfigRepo,
        trade_repo: TradeRepo,
        fund_repo: FundRepo,
        nav_provider: NavProvider,
        sender: ReportSender,
    ) -> None:
        self.alloc_repo = alloc_repo
        self.trade_repo = trade_repo
        self.fund_repo = fund_repo
        self.nav_provider = nav_provider
        self.sender = sender

    def build(self, mode: str = "market") -> str:
        """
        构造日报文本内容。

        Args:
            mode: 视图模式，`market`（市值）或 `shares`（份额），默认 `market`。

        Returns:
            文本格式的日报内容。
        """
        if mode not in {"market", "shares"}:
            raise ValueError("mode 仅支持 market 或 shares")

        target_weights = self.alloc_repo.get_target_weights()
        position_shares = self.trade_repo.position_shares()

        report_data = (
            self._build_market_view(position_shares, target_weights)
            if mode == "market"
            else self._build_share_view(position_shares, target_weights)
        )

        return self._render(report_data, target_weights)

    def _build_market_view(
        self,
        position_shares: Dict[str, Decimal],
        target_weights: Dict[AssetClass, Decimal],
    ) -> ReportData:
        """
        构造市值视图数据：按“确认为准的份额 × 当日 NAV”聚合市值与权重。

        规则：`nav is None or nav <= 0` 视为缺失，该基金不计入市值/权重，并记录在 missing_nav。
        """
        today = date.today()
        class_values: Dict[AssetClass, Decimal] = {}
        missing_nav: List[str] = []

        for fund_code, shares in position_shares.items():
            fund = self.fund_repo.get_fund(fund_code)
            if not fund:
                continue

            nav = self.nav_provider.get_nav(fund_code, today)
            if nav is None or nav <= Decimal("0"):
                missing_nav.append(fund_code)
                continue

            value = shares * nav
            asset_class = fund["asset_class"]
            class_values[asset_class] = class_values.get(asset_class, Decimal("0")) + value

        total_value = sum(class_values.values(), Decimal("0"))
        class_weight: Dict[AssetClass, Decimal] = {}
        if total_value > Decimal("0"):
            for asset_class, value in class_values.items():
                class_weight[asset_class] = value / total_value

        deviation = calc_weight_difference(class_weight, target_weights)

        return ReportData(
            mode="market",
            as_of=today,
            total_value=total_value,
            class_value=class_values,
            class_weight=class_weight,
            deviation=deviation,
            missing_nav=missing_nav,
        )

    def _build_share_view(
        self,
        position_shares: Dict[str, Decimal],
        target_weights: Dict[AssetClass, Decimal],
    ) -> ReportData:
        """
        构造份额视图数据：按已确认份额聚合各资产类别份额并计算权重（不依赖 NAV）。
        """
        class_shares: Dict[AssetClass, Decimal] = {}
        for fund_code, shares in position_shares.items():
            fund = self.fund_repo.get_fund(fund_code)
            if not fund:
                continue
            asset_class = fund["asset_class"]
            class_shares[asset_class] = class_shares.get(asset_class, Decimal("0")) + shares

        total_shares = sum(class_shares.values(), Decimal("0"))
        class_weight: Dict[AssetClass, Decimal] = {}
        if total_shares > Decimal("0"):
            for asset_class, shares in class_shares.items():
                class_weight[asset_class] = shares / total_shares

        deviation = calc_weight_difference(class_weight, target_weights)

        return ReportData(
            mode="shares",
            as_of=date.today(),
            total_value=total_shares,
            class_value=class_shares,
            class_weight=class_weight,
            deviation=deviation,
            missing_nav=[],
        )

    def _render(self, data: ReportData, target: Dict[AssetClass, Decimal]) -> str:
        """
        将 ReportData 渲染成文本格式。

        说明：再平衡提示阈值当前固定为 ±5%（未读取配置）。
        """
        lines: List[str] = []

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

            lines.append(
                f"- {asset_class.value}：{actual_pct:.1f}% (目标 {target_pct:.1f}%，{status})\n"
            )

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

        if data.mode == "market" and data.missing_nav:
            lines.append("\nNAV 缺失（未计入市值）：\n")
            for code in data.missing_nav:
                lines.append(f"- {code}\n")

        return "".join(lines)

    def send(self, mode: str = "market") -> bool:
        """
        发送日报（默认市值模式）。

        Args:
            mode: 视图模式，`market` 或 `shares`。

        Returns:
            发送是否成功。
        """
        return self.sender.send(self.build(mode=mode))
