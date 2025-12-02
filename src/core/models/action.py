from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

ActionType = Literal["buy", "sell", "dca_skip", "cancel"]
"""行为类型枚举。"""

Actor = Literal["human", "assistant", "system"]
"""行为主体枚举。"""

Intent = Literal["planned", "impulse", "opportunistic", "exit", "rebalance"]
"""意图标签枚举。"""

ActionSource = Literal["manual", "import", "automation", "migration"]
"""行为来源枚举：手动、导入、自动规则、迁移等。"""


@dataclass(slots=True)
class ActionLog:
    """
    用户行为日志，记录每一次与投资相关的“决策行为”。

    用途：
    - 为 AI 分析提供结构化行为数据（时间序列 + 标签）
    - 记录操作意图和人话备注（note）

    字段说明：
    - action: 行为类型（buy/sell/dca_skip/cancel）
    - actor: 行为主体（human/assistant/system），当前仅使用 human
    - source: 行为来源（manual/import/automation/migration）
    - acted_at: 行为发生时间（高精度时间戳）
    - fund_code: 关联基金代码（可空，DCA 跳过/导入场景尤为重要）
    - target_date: 行为针对的“交易日/计划日”（如定投日期），可空
    - trade_id: 关联 trades.id（可空，buy/sell/cancel 时通常非空）
    - intent: 意图标签，手动或流程写入（planned/impulse/opportunistic/exit/rebalance）
    - note: 人话备注，手动填写或系统说明

    设计原则：
    - 只记录用户的“决策行为”，不记录纯系统自动处理（如定投自动下单）
    - 不重复存储快照/结果，持仓与收益等从 trades/navs 动态计算
    - DCA 相关决策（如跳过某日定投）必须能通过 fund_code + target_date 唯一定位

    TODO:
        - v1 行为分析阶段，引入 ContextSnapshot / Outcome 等表，
          通过 action_log.id 作为统一锚点进行关联。
        - 如需支持多账户/多组合，可在 ActionLog 中新增 account_id/portfolio_id 字段。
    """

    id: int | None
    action: ActionType
    actor: Actor
    source: ActionSource
    acted_at: datetime
    fund_code: str | None = None
    """关联的基金代码（可空）。"""
    target_date: date | None = None
    """行为针对的交易日/计划日（如定投日期），可空。"""
    trade_id: int | None = None
    """关联的交易主键 ID（若有）。"""
    intent: Intent | None = None
    """操作意图标签，供 AI 分析使用。"""
    note: str | None = None
    """人话备注，自由文本。"""
