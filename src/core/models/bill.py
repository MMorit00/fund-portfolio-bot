"""账单导入数据模型。

设计原则：系统只输出事实，AI 负责推断。
- BillItem: CSV 解析后的单条记录
- AmountPhase: 金额阶段（压缩，按变化点切分）
- BillFacts: 事实快照（供 AI 分析，控制 token）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

# ============ 类型定义 ============

BillTradeType = Literal["dca_buy", "normal_buy"]
"""账单交易类型：dca_buy=定投买入, normal_buy=用户买入"""

# CSV 交易类型 → BillTradeType 映射
TRADE_TYPE_MAP: dict[str, BillTradeType] = {
    "定投买入": "dca_buy",
    "用户买入": "normal_buy",
}


class BillErrorCode(Enum):
    """账单解析错误码。"""

    UNKNOWN_TRADE_TYPE = "unknown_trade_type"  # 未知交易类型
    INVALID_AMOUNT = "invalid_amount"  # 金额解析失败
    INVALID_DATE = "invalid_date"  # 日期解析失败
    MISSING_FUND_CODE = "missing_fund_code"  # 缺少基金代码
    ROW_PARSE_ERROR = "row_parse_error"  # 行解析错误（字段数不匹配）


# ============ 解析记录 ============


@dataclass(slots=True)
class BillItem:
    """CSV 解析后的单条账单记录。

    字段直接映射 CSV 列，已做类型转换和清理。
    """

    order_id: str  # 订单号（已清理空格）
    trade_time: datetime  # 交易时间
    trade_type: BillTradeType  # 交易类型
    fund_name: str  # 基金名称（已清理换行符）
    fund_code: str  # 基金代码
    apply_amount: Decimal  # 申请金额
    confirm_amount: Decimal  # 确认金额
    confirm_shares: Decimal  # 确认份额
    fee: Decimal  # 手续费
    confirm_date: date  # 确认日期

    error_type: BillErrorCode | None = None  # 解析错误（可选）


@dataclass(slots=True)
class BillParseError:
    """账单解析错误记录。"""

    row_num: int  # 行号（1-indexed）
    error_type: BillErrorCode
    raw_data: str  # 原始行内容
    message: str  # 错误详情


# ============ 压缩统计 ============


@dataclass(slots=True)
class AmountPhase:
    """金额阶段（压缩，按变化点切分）。

    用于识别多阶段 DCA 模式（例如：80元→40元→20元）。
    变化阈值：金额变化 >10% 视为新阶段。

    特殊情况：同一天多笔不同金额 → 单独成一个阶段，amounts 列出所有金额。
    """

    start: date  # 阶段开始日期
    end: date  # 阶段结束日期
    apply_amt: Decimal  # 该阶段申请金额（众数）
    confirm_amt: Decimal  # 该阶段确认金额（众数）
    count: int  # 交易笔数
    fee: Decimal  # 该阶段总手续费
    amounts: list[Decimal] | None = None  # 同一天多笔不同金额时列出


@dataclass(slots=True)
class Anomaly:
    """异常交易（按天/类型分组）。

    kind:
    - "spike": 大额突变（偏离众数 >50%）
    - "gap": 长时间间隔（>30 天）

    数值特征与文字说明分开，AI 可基于数值自己解释。
    """

    id: int  # 组 ID
    kind: str  # 异常类型
    day: date  # 发生日期
    values: dict[str, str]  # 数值特征（例如：amount, phase_amt）
    note: str  # 简短说明


# ============ 事实快照 ============


@dataclass(slots=True)
class BillFacts:
    """账单事实快照（单基金）。

    设计原则：
    - 压缩统计，不给原始序列（控制 token）
    - phases 是核心（多阶段识别）
    - 异常做成结构化的"问题"（供 AI 审查）

    数量控制：
    - MAX_PHASES = 10（每只基金最多阶段数）
    - MAX_ANOMALIES_PER_KIND = 2（每种异常最多采样）
    """

    code: str  # 基金代码
    name: str  # 基金名称

    # 交易类型统计（直接从 CSV 字段）
    dca_count: int  # 定投买入笔数
    normal_count: int  # 用户买入笔数

    # 时间范围
    first: date  # 最早交易日
    last: date  # 最晚交易日

    # 金额阶段（压缩，MAX_PHASES=10）
    phases: list[AmountPhase] = field(default_factory=list)

    # 间隔分布（桶化）
    # 桶配置："1", "2-3", "4-6", "7", "8-14", "15-29", "30", ">30"
    gaps: dict[str, int] = field(default_factory=dict)

    # 周期分布
    weekdays: dict[str, int] = field(default_factory=dict)

    # 费用汇总
    total_fee: Decimal = Decimal("0")
    total_apply: Decimal = Decimal("0")
    total_confirm: Decimal = Decimal("0")

    # 异常（采样，MAX_ANOMALIES_PER_KIND=2）
    anomalies: list[Anomaly] = field(default_factory=list)
    anomaly_total: int = 0  # 实际异常总数（可能 > len(anomalies)）


@dataclass(slots=True)
class BillSummary:
    """账单汇总（多基金）。"""

    total_funds: int  # 基金数量
    total_trades: int  # 交易总数
    total_dca: int  # 定投买入总数
    total_normal: int  # 用户买入总数
    first: date | None  # 最早交易日
    last: date | None  # 最晚交易日
    total_fee: Decimal  # 总手续费
    total_apply: Decimal  # 总申请金额
    total_confirm: Decimal  # 总确认金额

    # 各基金事实
    facts: list[BillFacts] = field(default_factory=list)

    # 解析错误
    errors: list[BillParseError] = field(default_factory=list)
