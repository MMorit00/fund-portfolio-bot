from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from src.core.models.asset_class import AssetClass
from src.core.models.trade import MarketType


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
    alias: str | None = None
    """平台完整基金名称（用于导入时匹配）。"""


@dataclass(slots=True)
class RedemptionFeeTier:
    """
    赎回费阶梯。

    按持有天数区分不同的赎回费率。
    """

    min_hold_days: int
    """最小持有天数（含）。"""
    max_hold_days: int | None
    """最大持有天数（不含），None 表示无上限。"""
    rate: Decimal
    """赎回费率（百分比，如 1.50 表示 1.50%）。"""


@dataclass(slots=True)
class FundFees:
    """
    基金费率信息（聚合视图）。

    设计说明：
    - 当前是"聚合视图"，隐藏了表中的 fee_type/charge_basis 字段
    - fee_type 被编码到字段名中（management_fee/custody_fee 等）
    - charge_basis 被隐含：management/custody/service 是 annual，purchase/redemption 是 transaction
    - 优点：业务层使用简单，直接问"管理费多少？赎回阶梯如何？"
    - 缺点：如需按 charge_basis 统计、或直接操作单条费率，需要额外方法

    TODO: 如果将来有以下需求，可考虑新增 FundFeeItem 数据类：
    - 需要在业务层区分"按年收 vs 按笔收"的费用分类统计
    - 需要直接操作"单条费率记录"而非聚合视图
    - 需要动态新增 fee_type 而不修改 FundFees 字段
    """

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
    redemption_tiers: list[RedemptionFeeTier] = field(default_factory=list)
    """赎回费阶梯（按 min_hold_days 升序排列）。"""
