from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from src.core.asset_class import AssetClass
from src.core.dca_plan import DcaPlan
from src.core.trade import MarketType, Trade


@dataclass(slots=True)
class FundInfo:
    """
    基金信息数据类。

    包含基金代码、名称、资产类别和市场类型。
    """

    fund_code: str
    name: str
    asset_class: AssetClass
    market: MarketType


class FundRepo(Protocol):
    """
    基金与资产类别相关的读取/写入。

    约定：`asset_class` 使用 AssetClass 枚举；`market` 仅支持 "A" / "QDII"。
    """

    def add_fund(self, fund_code: str, name: str, asset_class: AssetClass, market: str) -> None:
        """
        新增或更新基金信息（按 fund_code 幂等）。

        Args:
            fund_code: 基金代码（主键）。
            name: 基金名称。
            asset_class: 资产类别。
            market: 市场标识，"A" 或 "QDII"。
        """

    def get_fund(self, fund_code: str) -> FundInfo | None:
        """
        按基金代码读取信息。

        Returns:
            FundInfo 对象，未找到返回 None。
        """

    def list_funds(self) -> list[FundInfo]:
        """按 fund_code 排序返回全部基金信息列表。"""


class AllocConfigRepo(Protocol):
    """
    资产配置目标权重与偏离阈值，取值均为 0..1 的小数。
    """

    def get_target_weights(self) -> dict[AssetClass, Decimal]:
        """返回各资产类别的目标权重。"""

    def get_max_deviation(self) -> dict[AssetClass, Decimal]:
        """返回各资产类别允许的最大偏离阈值。"""


class TradeRepo(Protocol):
    """交易存取。金额/份额使用 Decimal。"""

    def add(self, trade: Trade) -> Trade:
        """新增 pending 交易（实现可预写 confirm_date），返回带 id 的 Trade。"""

    def list_pending_to_confirm(self, confirm_date: date) -> list[Trade]:
        """按预写的确认日筛选 pending 交易，返回待确认列表。"""

    def confirm(self, trade_id: int, shares: Decimal, nav: Decimal) -> None:
        """将交易更新为 confirmed，并写入份额与用于确认的 NAV。"""

    def position_shares(self) -> dict[str, Decimal]:
        """聚合已确认交易，返回净持仓份额（fund_code -> shares）。"""

    def skip_dca_for_date(self, fund_code: str, day: date) -> int:
        """将指定日期的 pending 买入定投标记为 skipped，返回影响行数。"""


class NavProvider(Protocol):
    """外部数据源：按日期获取官方单位净值。"""

    def get_nav(self, fund_code: str, day: date) -> Decimal | None:
        """
        读取指定基金在给定日期的官方单位净值。

        Returns:
            Decimal 净值；无数据返回 None。
        """


class NavRepo(Protocol):
    """净值存取（可选：只使用 provider 也可）。"""

    def upsert(self, fund_code: str, day: date, nav: Decimal) -> None:
        """插入或更新某日净值（fund_code+day 幂等）。"""

    def get(self, fund_code: str, day: date) -> Decimal | None:
        """读取某日净值，未找到返回 None。"""


class DcaPlanRepo(Protocol):
    """定投计划存取。"""

    def list_due_plans(self, day: date) -> list[DcaPlan]:
        """
        列出当天需检查的定投计划。

        说明：MVP 实现可返回全部计划，由用例判定"是否到期"。
        """

    def get_plan(self, fund_code: str) -> DcaPlan | None:
        """读取某基金的定投计划，未配置返回 None。"""


class ReportSender(Protocol):
    """报告发送（例如 Discord Webhook）。"""

    def send(self, text: str) -> bool:
        """发送文本报告，返回是否成功。"""
