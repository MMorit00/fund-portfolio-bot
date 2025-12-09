"""历史账单导入数据模型。

详细设计见 docs/history-import.md。

设计原则：
- 聚焦两个核心数据对象：ImportItem（IR）与 ImportResult（报告）；
- 复用全局类型定义（TradeType, TradeStatus, MarketType）；
- 单一数据源：trade_time 派生 trade_date，避免冗余字段；
- 预存 market，写库前无需额外查询，确保数据闭环。

v0.4.3 新增：
- ImportBatch：导入批次记录，用于追溯和撤销。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from src.core.models.trade import MarketType, TradeStatus, TradeType

# 导入来源（只保留已规划的平台）
ImportSource = Literal["alipay", "ttjj"]

# 错误类型
ImportErrorCode = Literal[
    "parse_error",      # CSV 解析失败（格式错误、编码问题）
    "fund_not_found",   # 基金外部名称映射失败
    "nav_missing",      # NAV 抓取失败
    "invalid_data",     # 数据校验失败（金额为负等）
    "duplicate",        # 重复记录
]


@dataclass(slots=True)
class ImportBatch:
    """
    导入批次记录（v0.4.3 新增）。

    用途：
    - 作为"撤销点"和"追溯源"，确保每次历史导入都有明确边界；
    - 支持批次级别的撤销、重跑、查询（WHERE import_batch_id = ?）；
    - 手动/自动交易不关联批次（import_batch_id = NULL）。

    生命周期：
    - 在 import_trades_from_file() 开始时创建（mode='apply'）；
    - 返回的 batch_id 传递给后续 Trade 写入流程；
    - 写入 import_batches 表后不再修改。
    """

    source: ImportSource
    """来源平台（alipay / ttjj）。"""

    created_at: datetime
    """创建时间（ISO 格式）。"""

    id: int | None = None
    """批次 ID（写入数据库后自动生成）。"""

    note: str | None = None
    """可选备注（用于记录导入文件路径等）。"""


@dataclass(slots=True)
class ImportItem:
    """
    导入记录（统一承载：解析 → 映射 → 补充 → 写库）。

    生命周期：
    1. 解析阶段：填充原始字段（external_id, raw_fund_name, ...）
    2. 映射阶段：填充 fund_code, market
    3. NAV 阶段：填充 nav, shares
    4. 写库阶段：根据 target_status 写入 trades

    状态映射（支付宝 → Trade.status）：
    - "交易成功" → confirmed
    - "付款成功，份额确认中" → pending
    - "交易关闭" → 跳过（不创建 ImportItem）
    """

    # === 原始数据（CSV 解析，必填） ===
    source: ImportSource
    """来源平台（用于 trades.remark 和 action_log.note）。"""

    external_id: str
    """交易号，用于去重（trades.external_id 唯一约束）。"""

    raw_fund_name: str
    """
    原始基金名称，用于外部名称映射和调试。

    TODO: 中长期配合 FundNameMapping，将该字段的使用从直接查询 funds.alias
    迁移到独立的名称映射仓储。
    """

    trade_type: TradeType
    """交易类型：buy / sell（从商品名称末尾解析）。"""

    trade_time: datetime
    """交易时间，精确到秒（用于 action_log.acted_at）。"""

    amount: Decimal
    """交易金额（元）。"""

    target_status: TradeStatus
    """目标交易状态：confirmed / pending（从支付宝状态映射）。"""

    # === 映射数据（FundRepo 查询后填充） ===
    fund_code: str | None = None
    """基金代码（通过基金外部名称映射得到，当前实现依赖 funds.alias 字段）。"""

    market: MarketType | None = None
    """市场类型（写 Trade 需要，从 funds.market 获取）。"""

    # === 补充数据（NAV 抓取后填充） ===
    nav: Decimal | None = None
    """净值（从东方财富抓取）。"""

    shares: Decimal | None = None
    """份额（计算得出：amount / nav）。"""

    # === 错误状态 ===
    error_type: ImportErrorCode | None = None
    """错误类型（None 表示无错误）。"""

    error_message: str | None = None
    """错误详情。"""

    # === 降级标记 ===
    was_downgraded: bool = False
    """是否因 NAV 缺失从 confirmed 自动降级为 pending。"""

    @property
    def trade_date(self) -> date:
        """交易日期（从 trade_time 派生，保持单一数据源）。"""
        return self.trade_time.date()

    @property
    def is_valid(self) -> bool:
        """是否可以导入（无错误 + 必要字段齐全）。"""
        return (
            self.error_type is None
            and self.fund_code is not None
            and self.market is not None
        )

    @property
    def can_confirm(self) -> bool:
        """是否可以直接确认（有 NAV + 有份额）。"""
        return (
            self.is_valid
            and self.nav is not None
            and self.shares is not None
            and self.target_status == "confirmed"
        )


@dataclass(slots=True)
class ImportResult:
    """
    导入结果汇总。

    只存储统计数据，不存储输入参数（mode/csv_path 等由调用者管理）。
    额外字段包括：
    - downgraded: 因 NAV 缺失自动降级为 pending 的数量；
    - fund_mapping: 基金映射摘要；
    - error_summary: 错误分类统计；
    - batch_id: 本次导入创建的批次 ID（v0.4.3 新增）。
    """

    total: int = 0
    """识别到的基金交易总数（不含"交易关闭"）。"""

    succeeded: int = 0
    """成功导入（写入 trades 表）。"""

    failed: int = 0
    """失败（映射失败 / NAV 缺失 / 数据校验失败）。"""

    skipped: int = 0
    """跳过（重复记录）。"""

    downgraded: int = 0
    """因 NAV 缺失自动降级为 pending 的数量。"""

    failed_records: list[ImportItem] = field(default_factory=list)
    """失败记录详情（用于错误报告，只存失败的）。"""

    fund_mapping: dict[str, tuple[str, str]] = field(default_factory=dict)
    """基金映射摘要：{raw_fund_name: (fund_code, fund_name)}。"""

    error_summary: dict[str, int] = field(default_factory=dict)
    """错误分类统计：{error_type: count}。"""

    batch_id: int | None = None
    """本次导入创建的 import_batches.id；仅在 mode='apply' 时非空。"""

    @property
    def success_rate(self) -> float:
        """成功率（0.0 ~ 1.0）。"""
        if self.total == 0:
            return 0.0
        return self.succeeded / self.total
