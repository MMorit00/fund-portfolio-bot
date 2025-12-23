from .action import ActionLog, ActionSource, ActionType, Actor, Intent, Strategy
from .alloc_config import AllocConfig
from .asset_class import AssetClass
from .bill import (
    TRADE_TYPE_MAP,
    AmountPhase,
    BillErrorCode,
    BillFacts,
    BillItem,
    BillParseError,
    BillSummary,
    BillTradeType,
)
from .bill import (
    Anomaly as BillAnomaly,
)
from .dca_backfill import (
    Anomaly,
    BackfillResult,
    BatchSummary,
    Bucket,
    DayCheck,
    DcaFacts,
    Segment,
    Skipped,
)
from .dca_plan import DcaPlan, Frequency, Status
from .fund import Fund, FundFees, RedemptionTier
from .import_batch import ImportBatch, ImportSource
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
    # DCA 回填
    "Anomaly",
    "BackfillResult",
    "BatchSummary",
    "Bucket",
    "DayCheck",
    "DcaFacts",
    "Segment",
    "Skipped",
    # 账单导入
    "BillItem",
    "BillFacts",
    "BillSummary",
    "BillParseError",
    "BillErrorCode",
    "BillTradeType",
    "BillAnomaly",
    "AmountPhase",
    "TRADE_TYPE_MAP",
    # 导入批次
    "ImportBatch",
    "ImportSource",
    # NAV 与结算策略
    "NavQuality",
    "SettlementPolicy",
    # 行为日志
    "ActionLog",
    "ActionSource",
    "ActionType",
    "Actor",
    "Intent",
    "Strategy",
]
