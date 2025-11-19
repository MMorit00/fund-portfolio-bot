from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Protocol

from src.core.asset_class import AssetClass
from src.core.dca_plan import DcaPlan
from src.core.fund import FundInfo
from src.core.trade import Trade

# ============================================================================
# Repository 接口（数据访问层协议）
# ============================================================================


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

    def update(self, trade: Trade) -> None:
        """更新交易记录（v0.2.1：支持延迟追踪字段更新）。"""

    def list_recent_trades(self, days: int = 7) -> list[Trade]:
        """列出最近 N 天的交易（v0.2.1：用于日报展示）。"""

    def position_shares(self) -> dict[str, Decimal]:
        """聚合已确认交易，返回净持仓份额（fund_code -> shares）。"""

    def skip_dca_for_date(self, fund_code: str, day: date) -> int:
        """将指定日期的 pending 买入定投标记为 skipped，返回影响行数。"""


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


# ============================================================================
# Service 接口（领域服务协议）
# ============================================================================


class NavProtocol(Protocol):
    """
    NAV 查询协议（运行时本地查询）。

    用于确认用例、日报、再平衡等需要读取本地已存储的净值数据的场景。
    """

    def get_nav(self, fund_code: str, day: date) -> Decimal | None:
        """
        读取指定基金在给定日期的官方单位净值。

        Returns:
            Decimal 净值；无数据返回 None。
        """


class NavSourceProtocol(Protocol):
    """
    NAV 数据源协议（外部抓取）。

    用于从 HTTP、CSV 等外部来源拉取净值数据。
    实现者负责从数据源获取 NAV，但不负责持久化（持久化由 UseCase 调用 NavRepo 完成）。
    """

    def get_nav(self, fund_code: str, day: date) -> Decimal | None:
        """
        从外部数据源获取指定基金在给定日期的官方单位净值。

        Returns:
            Decimal 净值；无数据或失败返回 None。
        """


class ReportProtocol(Protocol):
    """报告发送协议（例如 Discord Webhook、邮件等）。"""

    def send(self, text: str) -> bool:
        """发送文本报告，返回是否成功。"""


class CalendarProtocol(Protocol):
    """
    交易日历协议：判断开市日 + T+N 偏移计算。

    使用 calendar_key（如 "CN_A"、"US_NYSE"）标识不同市场的交易日历。
    """

    def is_open(self, calendar_key: str, day: date) -> bool:
        """
        判断指定日期是否为交易日。

        Args:
            calendar_key: 日历标识（如 "CN_A"、"US_NYSE"）。
            day: 待判断的日期。

        Returns:
            True 表示交易日，False 表示休市日。
        """

    def next_open(self, calendar_key: str, day: date) -> date:
        """
        返回 >= day 的首个交易日（含当日）。

        or_self 语义：如果 day 本身是交易日，返回 day；否则向后找最近的交易日。

        Args:
            calendar_key: 日历标识。
            day: 参考日期。

        Returns:
            首个交易日。

        Raises:
            RuntimeError: 若在合理范围内（如 365 天）未找到交易日。
        """

    def shift(self, calendar_key: str, day: date, n: int) -> date:
        """
        从 day 向后偏移 n 个交易日（T+N）。

        无论 day 是否开市，都从 day 往后数 n 个"交易日"。
        用于计算确认日等场景：confirm_date = calendar.shift(key, pricing_date, settle_lag)。

        Args:
            calendar_key: 日历标识。
            day: 起始日期。
            n: 偏移量（必须 >= 1）。

        Returns:
            偏移后的交易日。

        Raises:
            ValueError: 若 n < 1。
            RuntimeError: 若在合理范围内未能完成偏移。
        """
