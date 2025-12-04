"""DCA 回填数据模型（v0.4.3）。

用途：
- 将历史导入的交易标记为 DCA 归属（trades.dca_plan_key）
- 更新行为日志策略标签（action_log.strategy）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(slots=True)
class BackfillMatch:
    """单笔交易的匹配结果。"""

    trade_id: int
    """交易 ID。"""

    fund_code: str
    """基金代码。"""

    trade_date: str
    """交易日期（ISO 格式）。"""

    amount: Decimal
    """交易金额。"""

    matched: bool
    """是否匹配到 DCA 计划。"""

    dca_plan_key: str | None = None
    """匹配到的 DCA 计划标识（当前格式=fund_code）。"""

    match_reason: str | None = None
    """匹配原因说明（如"日期+金额匹配"/"金额超出±10%容差"等）。"""


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

    matches: list[BackfillMatch] = field(default_factory=list)
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
