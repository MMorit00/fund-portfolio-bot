from __future__ import annotations

from dataclasses import dataclass

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
    """

    fund_code: str
    name: str
    asset_class: AssetClass
    market: MarketType
    alias: str | None = None
    """平台完整基金名称（用于导入时匹配）。"""
