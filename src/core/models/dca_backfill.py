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
class DcaTradeCheck:
    """
    单笔交易的 DCA 规则检查结果（*Check 规范）。

    规则层只输出事实（日期匹配+金额偏差），不做语义判断。
    """

    trade_id: int
    """交易 ID。"""

    fund_code: str
    """基金代码。"""

    trade_date: str
    """交易日期（ISO 格式）。"""

    amount: Decimal
    """交易金额。"""

    matched: bool
    """是否归属 DCA（由日期决定，不考虑金额）。"""

    amount_deviation: Decimal = Decimal("0")
    """金额偏差率（事实字段）：正数=超出计划，负数=低于计划。如 0.15 表示超出15%。"""

    dca_plan_key: str | None = None
    """匹配到的 DCA 计划标识（当前格式=fund_code）。"""

    match_reason: str | None = None
    """匹配说明（日期+金额偏差等事实信息）。"""


@dataclass(slots=True)
class FundBackfillSummary:
    """单只基金的回填摘要。"""

    fund_code: str
    """基金代码。"""

    total_trades: int
    """总交易数（buy only）。"""

    matched_trades: int
    """匹配到 DCA 计划的交易数。"""

    has_dca_plan: bool
    """是否存在 DCA 计划（active/disabled 均算）。"""

    dca_plan_info: str | None = None
    """DCA 计划摘要（如"100 元/monthly/28 (active)"）。"""

    matches: list[DcaTradeCheck] = field(default_factory=list)
    """详细匹配结果（dry-run 模式使用）。"""


@dataclass(slots=True)
class BackfillResult:
    """
    DCA 回填结果汇总（v0.4.3）。

    字段说明：
    - batch_id: 导入批次 ID（作用范围）
    - mode: 运行模式（dry_run / apply）
    - total_trades: 批次内的总交易数（仅 buy）
    - matched_count: 匹配到 DCA 计划的交易数
    - updated_count: 实际更新的记录数（apply 模式）
    - fund_summaries: 按基金分组的回填摘要
    """

    batch_id: int
    """导入批次 ID。"""

    mode: str
    """运行模式：dry_run / apply。"""

    total_trades: int
    """批次内总交易数（仅 buy）。"""

    matched_count: int
    """匹配到 DCA 计划的交易数。"""

    updated_count: int = 0
    """实际更新的记录数（仅 apply 模式有值）。"""

    fund_summaries: list[FundBackfillSummary] = field(default_factory=list)
    """按基金分组的回填摘要。"""

    fund_code_filter: str | None = None
    """基金代码过滤（None=全部）。"""

    @property
    def match_rate(self) -> float:
        """匹配率（0.0 ~ 1.0）。"""
        if self.total_trades == 0:
            return 0.0
        return self.matched_count / self.total_trades


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
    first_amount: Decimal | None = None
    """首笔金额。"""

    last_amount: Decimal | None = None
    """末笔金额。"""

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
