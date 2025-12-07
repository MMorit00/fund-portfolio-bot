from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from src.core.models.dca_plan import Frequency

if TYPE_CHECKING:
    from src.core.models.fund_restriction import ParsedRestriction

Confidence = Literal["high", "medium", "low"]


@dataclass(slots=True)
class DcaPlanDraft:
    """
    从历史买入记录推断出的定投计划草案（*Draft 规范）。

    字段说明：
    - fund_code: 基金代码；
    - amount: 历史金额中位数（仅作参考建议，真实计划金额由用户通过 dca_plan add 确认）；
    - frequency: 频率（daily/weekly/monthly）；
    - rule: 规则（weekly=MON/TUE/...，monthly=1..31，daily 为空字符串）；
    - sample_count: 参与推断的样本数量（买入笔数）；
    - span_days: 样本覆盖天数（最早交易日到最晚交易日的天数差）；
    - confidence: 置信度等级（high/medium/low）。

    说明：
    - 本数据类是建议方案，永远不对应 DB 表，只是内存结构；
    - 由 draft_dca_plans() Flow 构建，供 CLI 展示和人工决策参考；
    - 推断结果需手动通过 dca_plan add 确认后才创建真实计划。
    """

    fund_code: str
    amount: Decimal
    frequency: Frequency
    rule: str
    sample_count: int
    span_days: int
    confidence: Confidence
    first_date: date
    last_date: date


@dataclass(slots=True)
class DcaInferResult:
    """
    DCA 推断结果（含推断草案 + 当前限额状态）。

    字段说明：
    - drafts: 推断的定投计划草案列表；
    - fund_restrictions: 各基金当前限额状态（fund_code → ParsedRestriction | None）。

    设计目标：
    - 为 AI 分析提供完整的上下文：历史推断 + 当前约束；
    - 帮助识别"金额变化是限额导致 vs 主动调整"。

    说明：
    - fund_restrictions[fund_code] = None 表示该基金当前无交易限制（开放申购）；
    - fund_restrictions[fund_code] = ParsedRestriction 表示存在限制（限购/暂停）。
    """

    drafts: list[DcaPlanDraft]
    fund_restrictions: dict[str, ParsedRestriction | None]

