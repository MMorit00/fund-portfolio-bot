from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from src.core.asset_class import AssetClass
from src.core.portfolio.rebalance import calc_weight_difference
from src.core.protocols import AllocConfigRepo, FundRepo, NavProtocol, ReportProtocol, TradeRepo
from src.core.trade import Trade

ReportMode = Literal["market", "shares"]


@dataclass
class ReportData:
    """
    日报数据结构（支持市值视图与份额视图）。

    口径：
    - 仅统计“已确认份额”，不包含当日 pending 交易；
    - 市值模式仅使用“当日官方 NAV”，`nav <= 0` 视为缺失；
    - 缺失 NAV 的基金不计入市值与权重分母，并在 missing_nav 中列出；
    - 不做“最近交易日 NAV”回退（v0.2 严格版），因此当日总市值可能被低估。

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
    # 统计字段：市值模式有效；份额模式下为 0
    total_funds_in_position: int
    funds_with_nav: int


class GenerateDailyReport:
    """
    生成并发送文本日报（市值/份额两种模式）。

    业务口径：
    - 仅统计“已确认份额”，不包含当日 pending；
    - 市值模式按“确认为准的份额 × 当日官方 NAV”计算；`nav <= 0` 视为缺失并在文末列出；
    - 缺失 NAV 的基金不参与市值累计与权重分母；
    - v0.2 严格版不做 NAV 回退；
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
        nav_provider: NavProtocol,
        sender: ReportProtocol,
    ) -> None:
        self.alloc_repo = alloc_repo
        self.trade_repo = trade_repo
        self.fund_repo = fund_repo
        self.nav_provider = nav_provider
        self.sender = sender

    def build(self, mode: ReportMode = "market", *, as_of: date | None = None) -> str:
        """
        构造日报文本内容。

        Args:
            mode: 视图模式，`market`（市值）或 `shares`（份额），默认 `market`。
            as_of: 展示日（通常为上一交易日）。未提供时由调用方决定默认值。

        Returns:
            文本格式的日报内容。
        """

        target_weights = self.alloc_repo.get_target_weights()
        position_shares = self.trade_repo.position_shares()

        # 由调用方传入 as_of，未传入时使用今天（调用方通常会提供上一交易日）
        eff_as_of = as_of or date.today()

        report_data = (
            self._build_market_view(position_shares, target_weights, eff_as_of)
            if mode == "market"
            else self._build_share_view(position_shares, target_weights, eff_as_of)
        )

        # v0.2.1: 获取最近交易用于确认情况展示
        recent_trades = self.trade_repo.list_recent_trades(days=7)

        return self._render(report_data, target_weights, recent_trades)

    def _build_market_view(
        self,
        position_shares: dict[str, Decimal],
        target_weights: dict[AssetClass, Decimal],
        as_of: date,
    ) -> ReportData:
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
            fund = self.fund_repo.get_fund(fund_code)
            if not fund:
                # 未配置基金：不计入分母，也不参与市值与缺失列表
                continue

            # 至此可确认该基金在 fund_repo 中有配置，计入分母
            total_funds_in_position += 1

            nav = self.nav_provider.get_nav(fund_code, today)
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

        deviation = calc_weight_difference(class_weight, target_weights)

        return ReportData(
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
        self,
        position_shares: dict[str, Decimal],
        target_weights: dict[AssetClass, Decimal],
        as_of: date,
    ) -> ReportData:
        """
        构造份额视图数据：按已确认份额聚合各资产类别份额并计算权重（不依赖 NAV）。
        """
        class_shares: dict[AssetClass, Decimal] = {}
        for fund_code, shares in position_shares.items():
            fund = self.fund_repo.get_fund(fund_code)
            if not fund:
                continue
            asset_class = fund.asset_class
            class_shares[asset_class] = class_shares.get(asset_class, Decimal("0")) + shares

        total_shares = sum(class_shares.values(), Decimal("0"))
        class_weight: dict[AssetClass, Decimal] = {}
        if total_shares > Decimal("0"):
            for asset_class, shares in class_shares.items():
                class_weight[asset_class] = shares / total_shares

        deviation = calc_weight_difference(class_weight, target_weights)

        return ReportData(
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

    def _render(
        self, data: ReportData, target: dict[AssetClass, Decimal], recent_trades: list[Trade]
    ) -> str:
        """
        将 ReportData 渲染成文本格式（v0.2.1：新增交易确认情况）。

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

        # v0.2.1: 交易确认情况
        confirmation_section = self._render_confirmation_status(recent_trades, data.as_of)
        if confirmation_section:
            lines.append(confirmation_section)

        if data.mode == "market" and data.missing_nav:
            # v0.2 严格版提示：当日 NAV 缺失会导致市值低估
            lines.append(
                f"\n提示：今日 {data.funds_with_nav}/{data.total_funds_in_position} 只基金有有效 NAV，总市值可能低估。\n"  # noqa: E501
            )
            lines.append("\nNAV 缺失（未计入市值）：\n")
            for code in data.missing_nav:
                lines.append(f"- {code}\n")

        return "".join(lines)

    def _render_confirmation_status(self, trades: list[Trade], today: date) -> str:
        """
        生成交易确认情况板块（v0.2.1）。

        分三类：
        1. 已确认（正常）
        2. 待确认（未到确认日）
        3. 异常延迟（已到确认日但 NAV 缺失）
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

        # 1. 已确认
        if confirmed_trades:
            lines.append(f"\n✅ 已确认（{len(confirmed_trades)}笔）\n")
            for t in confirmed_trades[:5]:  # 最近5笔
                trade_type_text = "买入" if t.type == "buy" else "卖出"
                lines.append(
                    f"  - {t.trade_date.strftime('%m-%d')} {trade_type_text} "
                    f"{t.fund_code} {t.amount:.2f}元 "
                    f"→ 已确认 {t.shares:.2f}份\n"
                )

        # 2. 待确认
        if waiting_trades:
            lines.append(f"\n⏳ 待确认（{len(waiting_trades)}笔）\n")
            for t in waiting_trades:
                trade_type_text = "买入" if t.type == "buy" else "卖出"
                if t.confirm_date:
                    days_until_confirm = (t.confirm_date - today).days
                    # 处理负天数情况（理论上不应出现，但防御性处理）
                    if days_until_confirm >= 0:
                        days_text = f"（还有{days_until_confirm}天）"
                    else:
                        days_text = f"（已过期{abs(days_until_confirm)}天，待补充净值/待确认）"

                    lines.append(
                        f"  - {t.trade_date.strftime('%m-%d')} {trade_type_text} "
                        f"{t.fund_code} {t.amount:.2f}元 "
                        f"→ 预计 {t.confirm_date.strftime('%m-%d')} 确认{days_text}\n"
                    )
                else:
                    lines.append(
                        f"  - {t.trade_date.strftime('%m-%d')} {trade_type_text} "
                        f"{t.fund_code} {t.amount:.2f}元 → 确认日待定\n"
                    )

        # 3. 异常延迟
        if delayed_trades:
            lines.append(f"\n⚠️ 异常延迟（{len(delayed_trades)}笔）\n")
            for t in delayed_trades:
                trade_type_text = "买入" if t.type == "buy" else "卖出"
                delayed_days = (today - t.confirm_date).days if t.confirm_date else 0

                lines.append(
                    f"  - {t.trade_date.strftime('%m-%d')} {trade_type_text} "
                    f"{t.fund_code} {t.amount:.2f}元\n"
                )
                if t.confirm_date:
                    lines.append(f"    理论确认日：{t.confirm_date.strftime('%Y-%m-%d')}\n")
                lines.append(f"    当前状态：确认延迟（已超过 {delayed_days} 天）\n")
                lines.append(f"    延迟原因：{self._get_delayed_reason_text(t.delayed_reason)}\n")
                lines.append(f"    建议：{self._get_delayed_suggestion(delayed_days)}\n")

        return "".join(lines)

    def _get_delayed_reason_text(self, reason: str | None) -> str:
        """延迟原因文案。"""
        if reason == "nav_missing":
            return "NAV 数据缺失（未获取到定价日官方净值）"
        return "原因未明"

    def _get_delayed_suggestion(self, delayed_days: int) -> str:
        """延迟建议文案。"""
        if delayed_days <= 2:
            return "等待 1-2 个工作日，基金公司可能延后披露净值"
        return "请到支付宝查看订单状态，如显示「确认中」则正常等待；如显示「失败/撤单」请及时在系统中标记"

    def send(self, mode: ReportMode = "market", *, as_of: date | None = None) -> bool:
        """
        发送日报（默认市值模式）。

        Args:
            mode: 视图模式，`market` 或 `shares`。
            as_of: 展示日（通常为上一交易日）。

        Returns:
            发送是否成功。
        """
        return self.sender.send(self.build(mode=mode, as_of=as_of))
