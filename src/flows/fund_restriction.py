"""
基金交易限制管理业务流程（v0.4.4）。

职责：
- 添加/结束限制记录
- 查询基金当前交易状态（AKShare）
- 将查询结果插入数据库
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.core.dependency import dependency
from src.core.models.fund_restriction import FundRestrictionFact, ParsedRestriction
from src.data.client.fund_data import FundDataClient
from src.data.db.fund_restriction_repo import FundRestrictionRepo


@dataclass
class AddRestrictionResult:
    """添加限制记录结果。"""

    record_id: int
    fund_code: str
    restriction_type: str
    start_date: date
    end_date: date | None
    limit_amount: Decimal | None


@dataclass
class EndRestrictionResult:
    """结束限制记录结果。"""

    success: bool
    fund_code: str
    restriction_type: str
    end_date: date


@dataclass
class CheckStatusResult:
    """查询交易状态结果。"""

    fund_code: str
    parsed: ParsedRestriction | None


@dataclass
class ApplyStatusResult:
    """应用交易状态结果。"""

    record_id: int
    fund_code: str
    restriction_type: str


@dependency
def add_restriction(
    *,
    fund_code: str,
    restriction_type: str,
    start_date: date,
    end_date: date | None = None,
    limit_amount: Decimal | None = None,
    note: str | None = None,
    source: str = "manual",
    source_url: str | None = None,
    fund_restriction_repo: FundRestrictionRepo | None = None,
) -> AddRestrictionResult:
    """
    添加限制记录。

    Args:
        fund_code: 基金代码。
        restriction_type: 限制类型（daily_limit / suspend / resume）。
        start_date: 开始日期。
        end_date: 结束日期（可选）。
        limit_amount: 限购金额（仅 daily_limit 时有值）。
        note: 备注说明。
        source: 数据来源（默认 manual）。
        source_url: 公告链接（可选）。
        fund_restriction_repo: 限制记录仓储（自动注入）。

    Returns:
        AddRestrictionResult 结果对象。

    Raises:
        ValueError: 参数验证失败。
    """
    # 1. 参数验证
    if restriction_type == "daily_limit" and limit_amount is None:
        raise ValueError("daily_limit 类型必须提供 limit_amount 参数")

    if restriction_type in ("suspend", "resume") and limit_amount is not None:
        # 忽略 limit_amount（静默处理）
        limit_amount = None

    # 2. 创建 Fact 对象
    fact = FundRestrictionFact(
        fund_code=fund_code,
        start_date=start_date,
        end_date=end_date,
        restriction_type=restriction_type,
        limit_amount=limit_amount,
        source=source,
        source_url=source_url,
        note=note,
    )

    # 3. 保存到数据库
    record_id = fund_restriction_repo.add(fact)

    # 4. 返回结果
    return AddRestrictionResult(
        record_id=record_id,
        fund_code=fund_code,
        restriction_type=restriction_type,
        start_date=start_date,
        end_date=end_date,
        limit_amount=limit_amount,
    )


@dependency
def end_restriction(
    *,
    fund_code: str,
    restriction_type: str,
    end_date: date,
    fund_restriction_repo: FundRestrictionRepo | None = None,
) -> EndRestrictionResult:
    """
    结束限制记录。

    Args:
        fund_code: 基金代码。
        restriction_type: 限制类型（daily_limit / suspend / resume）。
        end_date: 结束日期。
        fund_restriction_repo: 限制记录仓储（自动注入）。

    Returns:
        EndRestrictionResult 结果对象。
    """
    # 1. 结束最新的 active 限制
    success = fund_restriction_repo.end_latest_active(
        fund_code, restriction_type, end_date
    )

    # 2. 返回结果
    return EndRestrictionResult(
        success=success,
        fund_code=fund_code,
        restriction_type=restriction_type,
        end_date=end_date,
    )


@dependency
def check_trading_status(
    *,
    fund_code: str,
    fund_data_client: FundDataClient | None = None,
) -> CheckStatusResult:
    """
    查询基金当前交易状态（通过 AKShare）。

    Args:
        fund_code: 基金代码。
        fund_data_client: 基金远程数据客户端（自动注入）。

    Returns:
        CheckStatusResult 结果对象。
    """
    # 1. 查询交易状态
    parsed = fund_data_client.get_trading_restriction(fund_code)

    # 2. 返回结果
    return CheckStatusResult(
        fund_code=fund_code,
        parsed=parsed,
    )


@dependency
def apply_trading_status(
    *,
    fund_code: str,
    parsed: ParsedRestriction,
    fund_restriction_repo: FundRestrictionRepo | None = None,
) -> ApplyStatusResult:
    """
    将查询结果插入数据库。

    Args:
        fund_code: 基金代码。
        parsed: 解析结果对象。
        fund_restriction_repo: 限制记录仓储（自动注入）。

    Returns:
        ApplyStatusResult 结果对象。
    """
    # 1. 转换为 Fact 对象
    fact = parsed.to_fact(source="eastmoney_trading_status")

    # 2. 插入数据库
    record_id = fund_restriction_repo.add(fact)

    # 3. 返回结果
    return ApplyStatusResult(
        record_id=record_id,
        fund_code=fund_code,
        restriction_type=parsed.restriction_type,
    )
