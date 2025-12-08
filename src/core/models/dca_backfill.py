"""DCA 回填数据模型（v0.4.3）。

用途：
- 将历史导入的交易标记为 DCA 归属（trades.dca_plan_key）
- 更新行为日志策略标签（action_log.strategy）
- 为 AI 提供结构化事实快照（FundDcaFacts）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(slots=True)
class DcaDayCheck:
    """
    某天的 DCA 轨道检查结果（规则层输出，按天聚合）。

    用于 AI 驱动的回填流程：
    - 规则层输出每天的轨道检查结果
    - AI 根据 is_on_track + trade_count + amounts 决定如何回填
    """

    date: date
    """交易日期。"""

    is_on_track: bool
    """该天是否在定投轨道上（由日期规则决定）。"""

    trade_count: int
    """该天交易笔数。"""

    trade_ids: list[int] = field(default_factory=list)
    """该天交易 ID 列表。"""

    amounts: list[Decimal] = field(default_factory=list)
    """该天交易金额列表（与 trade_ids 顺序对应）。"""


@dataclass(slots=True)
class SkippedTrade:
    """被跳过的交易（供 AI 审核）。"""

    trade_id: int
    """交易 ID。"""

    fund_code: str
    """基金代码。"""

    trade_date: date
    """交易日期。"""

    amount: Decimal
    """交易金额。"""

    reason: str
    """跳过原因。"""


@dataclass(slots=True)
class BackfillDaysResult:
    """
    backfill_days 的详细返回结果（供 AI 审核）。

    包含：输入数、更新数、跳过的交易详情。
    """

    input_count: int
    """输入的交易数。"""

    updated_count: int
    """实际更新的交易数。"""

    skipped_trades: list[SkippedTrade] = field(default_factory=list)
    """被跳过的交易列表（金额不在有效集合内）。"""


@dataclass(slots=True)
class TradeFlag:
    """
    特殊交易标记（*Flag 规范）。

    规则识别的"值得注意"的点（异常、中断等），仅标记不定性，供 AI 分析。
    """

    trade_id: int
    """交易 ID。"""

    trade_date: date
    """交易日期。"""

    amount: Decimal
    """交易金额。"""

    flag_type: str
    """标记类型：amount_outlier / amount_change / interval_outlier。"""

    detail: str
    """人类可读说明（事实描述，不做结论）。"""


@dataclass(slots=True)
class FundDcaFacts:
    """
    单只基金的 DCA 事实快照（供 AI 分析使用）。

    规则层只输出事实，不做语义判断。AI 基于这些事实做：
    - 判断金额变化是限额还是策略调整
    - 识别异常交易模式
    - 生成分析报告

    未来扩展（v0.4.4+）：
    - 关联 fund_restrictions 表，标记 DCA 时间段内是否存在限额事件
    - 可选方案 1：增加字段 `restriction_events: list[FundRestrictionFact]`
    - 可选方案 2：单独提供 `build_dca_context_for_ai()` Flow 合并多种 Facts
    - 规则层只提供事实关联，语义判断交给 AI 层
    """

    fund_code: str
    """基金代码。"""

    batch_id: int | None
    """导入批次 ID（None=全部交易）。"""

    trade_count: int
    """交易笔数。"""

    # 时间范围
    first_date: date | None = None
    """首笔日期。"""

    last_date: date | None = None
    """末笔日期。"""

    # 金额统计
    mode_amount: Decimal | None = None
    """众数金额（出现最多的金额，用于识别异常）。"""

    # 最近稳定值（当前定投金额）
    stable_amount: Decimal | None = None
    """最近稳定金额（连续相同的最后 N 笔）。"""

    stable_since: date | None = None
    """稳定开始日期。"""

    stable_count: int = 0
    """稳定笔数。"""

    # 分布统计
    amount_histogram: dict[str, int] = field(default_factory=dict)
    """金额分布（金额 → 出现次数）。"""

    mode_interval: int = 1
    """众数间隔（最常见间隔天数）。"""

    interval_histogram: dict[int, int] = field(default_factory=dict)
    """间隔分布（天数 → 出现次数）。"""

    # 特殊交易
    flags: list[TradeFlag] = field(default_factory=list)
    """特殊交易标记列表（金额异常/变化点/间隔异常）。"""

    @property
    def amount_changed(self) -> bool:
        """金额是否有变化。"""
        return len(self.amount_histogram) > 1
