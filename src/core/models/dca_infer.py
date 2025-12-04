from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from src.core.models.dca_plan import Frequency

Confidence = Literal["high", "medium", "low"]


@dataclass(slots=True)
class DcaPlanCandidate:
    """
    从历史买入记录推断出的定投计划候选。

    字段说明：
    - fund_code: 基金代码；
    - amount: 推断的定投金额（中位数）；
    - frequency: 频率（daily/weekly/monthly）；
    - rule: 规则（weekly=MON/TUE/...，monthly=1..31，daily 为空字符串）；
    - sample_count: 参与推断的样本数量（买入笔数）；
    - span_days: 样本覆盖天数（最早交易日到最晚交易日的天数差）；
    - confidence: 置信度等级（high/medium/low）。

    说明：
    - 本数据类只用于“只读分析”，不会写回数据库；
    - 由 DCA 推断 Flow 构建，供 CLI 展示和人工决策参考。
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

