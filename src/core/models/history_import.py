"""历史账单导入数据模型。

v0.4.2 新增：支持从支付宝等平台导入历史基金交易。
详细设计见 docs/history-import.md

精简设计原则：
- 只保留 2 个类（ImportRecord + ImportResult）
- 复用全局类型定义（TradeType, TradeStatus, MarketType）
- 单一数据源（trade_time 派生 trade_date）
- 数据闭环（预存 market 避免写库时重复查询）
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
ImportErrorType = Literal[
    "parse_error",      # CSV 解析失败（格式错误、编码问题）
    "fund_not_found",   # alias 映射失败
    "nav_missing",      # NAV 抓取失败
    "invalid_data",     # 数据校验失败（金额为负等）
    "duplicate",        # 重复记录
]


@dataclass(slots=True)
class ImportRecord:
    """
    导入记录（统一承载：解析 → 映射 → 补充 → 写库）。

    生命周期：
    1. 解析阶段：填充原始字段（external_id, original_fund_name, ...）
    2. 映射阶段：填充 fund_code, market
    3. NAV 阶段：填充 nav, shares
    4. 写库阶段：根据 target_status 写入 trades

    状态映射（支付宝 → Trade.status）：
    - "交易成功" → confirmed
    - "付款成功，份额确认中" → pending
    - "交易关闭" → 跳过（不创建 ImportRecord）
    """

    # === 原始数据（CSV 解析，必填） ===
    source: ImportSource
    """来源平台（用于 trades.source 和 action_log.note）。"""

    external_id: str
    """交易号，用于 (source, external_id) 去重。"""

    original_fund_name: str
    """原始基金名称，用于 alias 映射和调试。"""

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
    """基金代码（通过 funds.alias 映射得到）。"""

    market: MarketType | None = None
    """市场类型（写 Trade 需要，从 funds.market 获取）。"""

    # === 补充数据（NAV 抓取后填充） ===
    nav: Decimal | None = None
    """净值（从东方财富抓取）。"""

    shares: Decimal | None = None
    """份额（计算得出：amount / nav）。"""

    # === 错误状态 ===
    error_type: ImportErrorType | None = None
    """错误类型（None 表示无错误）。"""

    error_message: str | None = None
    """错误详情。"""

    @property
    def trade_date(self) -> date:
        """交易日期（从 trade_time 派生，保持单一数据源）。"""
        return self.trade_time.date()

    @property
    def is_valid(self) -> bool:
        """
        是否可以导入（无错误 + 必要字段齐全）。

        注意：此属性只检查基础映射是否完成，不区分 target_status。
        - pending 记录：is_valid=True 即可写入（后续正常确认流程补 NAV）
        - confirmed 记录：应使用 is_ready_for_confirm 检查 NAV 和份额是否齐全
        """
        return (
            self.error_type is None
            and self.fund_code is not None
            and self.market is not None
        )

    @property
    def is_ready_for_confirm(self) -> bool:
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
    """

    total: int = 0
    """识别到的基金交易总数（不含"交易关闭"）。"""

    succeeded: int = 0
    """成功导入（写入 trades 表）。"""

    failed: int = 0
    """失败（映射失败 / NAV 缺失 / 数据校验失败）。"""

    skipped: int = 0
    """跳过（重复记录）。"""

    failed_records: list[ImportRecord] = field(default_factory=list)
    """失败记录详情（用于错误报告，只存失败的）。"""

    @property
    def success_rate(self) -> float:
        """成功率（0.0 ~ 1.0）。"""
        if self.total == 0:
            return 0.0
        return self.succeeded / self.total
