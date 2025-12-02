from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

Frequency = Literal["daily", "weekly", "monthly"]
Status = Literal["active", "disabled"]


@dataclass(slots=True)
class DcaPlan:
    """
    定投计划。

    - frequency: 定投频率（daily/weekly/monthly）
    - rule: 对 daily 可为空；weekly 用 MON/TUE/...；monthly 用 1..31
    - status: active（活跃）/ disabled（已禁用）
    """

    fund_code: str
    amount: Decimal
    frequency: Frequency
    rule: str
    status: Status = "active"
