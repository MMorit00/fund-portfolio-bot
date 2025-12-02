from .action import ActionLog, ActionType, Actor, Intent
from .alloc_config import AllocConfig
from .asset_class import AssetClass
from .dca_plan import DcaPlan, Frequency, Status
from .fund import Fund, FundFees, RedemptionTier
from .history_import import ImportErrorType, ImportRecord, ImportResult, ImportSource
from .nav import NavQuality
from .policy import SettlementPolicy
from .trade import MarketType, Trade, TradeStatus, TradeType

"""
领域模型聚合导出。

说明：
- 仅做名称聚合，不引入额外逻辑，便于上层模块统一引用；
- 现有代码可以继续从各子模块直接导入，后续可按需逐步收敛到本入口。
"""

__all__ = [
    # 交易与市场
    "Trade",
    "TradeType",
    "TradeStatus",
    "MarketType",
    # 基金与资产配置
    "Fund",
    "FundFees",
    "RedemptionTier",
    "AssetClass",
    "AllocConfig",
    # 定投计划
    "DcaPlan",
    "Frequency",
    "Status",
    # 历史导入
    "ImportRecord",
    "ImportResult",
    "ImportSource",
    "ImportErrorType",
    # NAV 与结算策略
    "NavQuality",
    "SettlementPolicy",
    # 行为日志
    "ActionLog",
    "ActionType",
    "Actor",
    "Intent",
]
