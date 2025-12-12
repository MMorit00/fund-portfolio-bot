"""DCA 回填与事实快照数据模型。

设计原则：算法只输出事实，不做推断。
- segments: 稳定片段（金额+间隔相对稳定的时期）
- buckets / gaps: 全局分布（金额、间隔）
- anomalies: 异常标记（供 AI 审查，限量采样）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

# ============ Backfill 相关 ============


@dataclass(slots=True)
class DayCheck:
    """某天的 DCA 轨道检查结果。"""

    day: date
    on_track: bool
    count: int
    ids: list[int] = field(default_factory=list)
    amounts: list[Decimal] = field(default_factory=list)


@dataclass(slots=True)
class Skipped:
    """被跳过的交易。"""

    id: int
    code: str
    day: date
    amount: Decimal
    reason: str


@dataclass(slots=True)
class BackfillResult:
    """backfill 返回结果。"""

    total: int
    updated: int
    skipped: list[Skipped] = field(default_factory=list)


# ============ Facts 相关（给 AI 看的事实快照）============


@dataclass(slots=True)
class Segment:
    """稳定片段（金额+间隔相对稳定的时期）。

    用于识别多阶段 DCA 模式（例如：1000元/天 → 500元/周 → 100元/月）。

    数量控制：Flow 层会限制每只基金最多输出 5-10 段，
    过于短小的片段会被过滤。
    """

    id: int
    start: date
    end: date
    count: int  # 该段内交易笔数

    # 典型模式
    amount: Decimal  # 典型金额（众数）
    gap: int  # 典型间隔（众数，单位：天）
    weekdays: dict[str, int]  # 该段内的周期分布

    # 示例（供 AI 抽查，最多 3 条）
    samples: list[tuple[date, Decimal]] = field(default_factory=list)


@dataclass(slots=True)
class Bucket:
    """金额区间。

    用于全局金额分布的直方图。
    桶配置示例：[0,200]、(200,800]、(800,1500]、>1500。
    """

    label: str  # "0-200" / "200-800" / ">1500"
    count: int
    pct: float  # 占比（0.0~1.0）


@dataclass(slots=True)
class Anomaly:
    """异常交易（按天/类型分组）。

    kind:
    - "spike": 大额突变（偏离众数 >50%）
    - "multi": 同一天多笔交易
    - "gap": 长时间间隔（>30 天）

    数值特征与文字说明分开，AI 可基于数值自己解释。
    """

    id: int  # 组 ID（一个异常可能涉及多笔交易）
    kind: str
    day: date
    trades: list[int]  # 涉及的 trade_ids
    amounts: list[Decimal]
    note: str  # 简短说明（例如："1000元，远超众数100元"）


@dataclass(slots=True)
class DcaFacts:
    """DCA 事实快照（单基金）。

    设计原则：
    - segments 是核心（多阶段 DCA 的基础）
    - 全局分布辅助（buckets, gaps, weekdays）
    - 异常做成结构化的"问题"（供后续 AI 交互使用）
    - 控制体量，避免爆 token
    """

    code: str
    batch: int  # batch_id
    buys: int
    sells: int

    # 时间
    first: date
    last: date
    days: int

    # 全局模式
    mode_amt: Decimal | None  # 全局众数金额
    mode_gap: int | None  # 全局众数间隔（天）

    # 金额分布
    top_amts: list[tuple[Decimal, int]] = field(default_factory=list)  # [(100, 12), (20, 7)]
    buckets: list[Bucket] = field(default_factory=list)  # 金额区间分布（只针对买入）

    # 间隔分布（相邻买入的天数差）
    # 桶配置："1", "2-3", "4-6", "7", "8-29", "30", ">30"
    gaps: dict[str, int] = field(default_factory=dict)

    # 周期分布
    weekdays: dict[str, int] = field(default_factory=dict)

    # 段（金额+间隔稳定片段）
    segments: list[Segment] = field(default_factory=list)

    # 异常（限量采样）
    # anomalies: 每种 kind 最多 2 条样本（用于展示和 AI 感知"长啥样"）
    # anomaly_total: 实际异常总数（可能 > len(anomalies)）
    anomalies: list[Anomaly] = field(default_factory=list)
    anomaly_total: int = 0

    # 限额（轻量上下文）
    limit: Decimal | None = None


@dataclass(slots=True)
class BatchSummary:
    """批次总览（简化行）。"""

    code: str
    buys: int
    start: date | None
    end: date | None
    mode_amt: Decimal | None
    anomaly_count: int
