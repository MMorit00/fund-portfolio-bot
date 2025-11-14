from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Protocol

from src.core.assets.classes import AssetClass
from src.core.dca.plan import DcaPlan
from src.core.trading.trade import Trade


class FundRepo(Protocol):
    """基金与资产类别相关的读取/写入。"""

    def add_fund(self, fund_code: str, name: str, asset_class: AssetClass, market: str) -> None: ...
    def get_fund(self, fund_code: str) -> Optional[Dict]: ...  # 返回 name/asset_class/market 等
    def list_funds(self) -> List[Dict]: ...


class AllocConfigRepo(Protocol):
    """资产配置目标权重与偏离阈值。权重均为 0..1 小数。"""

    def get_target_weights(self) -> Dict[AssetClass, Decimal]: ...
    def get_max_deviation(self) -> Dict[AssetClass, Decimal]: ...


class TradeRepo(Protocol):
    """交易存取。金额/份额使用 Decimal。"""

    def add(self, trade: Trade) -> Trade: ...
    def list_pending_to_confirm(self, confirm_date: date) -> List[Trade]: ...
    def confirm(self, trade_id: int, shares: Decimal, nav: Decimal) -> None: ...
    def position_shares(self) -> Dict[str, Decimal]: ...  # fund_code -> shares


class NavProvider(Protocol):
    """外部数据源：按日期获取官方单位净值。"""

    def get_nav(self, fund_code: str, day: date) -> Optional[Decimal]: ...


class NavRepo(Protocol):
    """净值存取（可选：只使用 provider 也可）。"""

    def upsert(self, fund_code: str, day: date, nav: Decimal) -> None: ...
    def get(self, fund_code: str, day: date) -> Optional[Decimal]: ...


class DcaPlanRepo(Protocol):
    """定投计划存取。"""

    def list_due_plans(self, day: date) -> List[DcaPlan]: ...
    def get_plan(self, fund_code: str) -> Optional[DcaPlan]: ...


class ReportSender(Protocol):
    """报告发送（例如 Discord Webhook）。"""

    def send(self, text: str) -> bool: ...

