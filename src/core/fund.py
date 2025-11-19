from __future__ import annotations

from dataclasses import dataclass

from src.core.asset_class import AssetClass
from src.core.trade import MarketType


@dataclass(slots=True)
class FundInfo:
    """
    基金基础信息数据类。

    包含基金代码、名称、资产类别和市场类型。
    用于在领域层和应用层传递基金元数据。
    """

    fund_code: str
    name: str
    asset_class: AssetClass
    market: MarketType
