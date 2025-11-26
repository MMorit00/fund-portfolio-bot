from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ActionType = Literal["buy", "sell", "dca_skip", "rebalance"]
Actor = Literal["human", "system", "dca"]
Intent = Literal["planned", "impulse", "opportunistic", "exit"]


@dataclass(slots=True)
class ActionLog:
    """
    用户行为日志，记录每一次投资操作。

    用途：
    - 为 AI 分析提供行为数据
    - 记录操作意图和人话备注

    字段说明：
    - action: 动作类型（buy/sell/dca_skip/rebalance）
    - actor: 执行者（human/system/dca）
    - intent: 意图标签，手动填写（planned/impulse/opportunistic/exit）
    - note: 人话备注，手动填写

    设计原则：
    - 只记录用户的"决策行为"，不记录系统自动处理
    - 确认结果从 trades 表查询（status/confirm_date）
    """

    id: int | None
    action: ActionType
    actor: Actor
    acted_at: datetime
    trade_id: int | None = None
    intent: Intent | None = None
    note: str | None = None
