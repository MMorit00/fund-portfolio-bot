from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.core.models.asset_class import AssetClass
from src.core.models.trade import MarketType


@dataclass(slots=True)
class FundInfo:
    """
    基金基础信息数据类。

    包含基金代码、名称、资产类别和市场类型。
    用于在领域层和应用层传递基金元数据。

    v0.4.2 新增：alias 字段，用于存储平台完整基金名称（如支付宝账单中的名称），
    支持历史账单导入时的名称映射。

    v0.4.3 新增：费率字段（management_fee, custody_fee, service_fee,
    purchase_fee, purchase_fee_discount）。
    """

    fund_code: str
    name: str
    asset_class: AssetClass
    market: MarketType
    alias: str | None = None
    """平台完整基金名称（用于导入时匹配）。"""
    management_fee: Decimal | None = None
    """管理费率（年化百分比，如 0.50 表示 0.50%）。"""
    custody_fee: Decimal | None = None
    """托管费率（年化百分比）。"""
    service_fee: Decimal | None = None
    """销售服务费率（年化百分比）。"""
    purchase_fee: Decimal | None = None
    """申购费率原费率（百分比）。"""
    purchase_fee_discount: Decimal | None = None
    """申购费率折扣后费率（百分比）。"""


@dataclass(slots=True)
class FundFees:
    """基金费率信息（从 Eastmoney 抓取）。"""

    management_fee: Decimal | None = None
    """管理费率（年化百分比）。"""
    custody_fee: Decimal | None = None
    """托管费率（年化百分比）。"""
    service_fee: Decimal | None = None
    """销售服务费率（年化百分比）。"""
    purchase_fee: Decimal | None = None
    """申购费率原费率（百分比）。"""
    purchase_fee_discount: Decimal | None = None
    """申购费率折扣后费率（百分比）。"""
