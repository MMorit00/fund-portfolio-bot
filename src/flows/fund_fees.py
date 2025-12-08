"""基金费率管理（v0.4.4 重构：独立 fee 表）"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.dependency import dependency
from src.core.models import FundFees, RedemptionTier
from src.data.client.fund_data import FundDataClient
from src.data.db.fund_fee_repo import FundFeeRepo
from src.data.db.fund_repo import FundRepo


@dataclass(slots=True)
class SyncFeesResult:
    """
    费率同步结果。
    
    包含多字段聚合：
    - success/failed: 统计计数
    - details: 详细列表 (fund_code, name, success)
    
    用于 CLI 展示同步进度和失败明细。
    """

    success: int
    failed: int
    details: list[tuple[str, str, bool]]  # (fund_code, name, success)


@dependency
def get_fund_fees(
    fund_code: str,
    *,
    fund_fee_repo: FundFeeRepo | None = None,
) -> FundFees | None:
    """
    获取基金费率信息。

    Args:
        fund_code: 基金代码。
        fund_fee_repo: 基金费率仓储（自动注入）。

    Returns:
        FundFees 对象或 None（无费率记录）。
    """
    return fund_fee_repo.get_fees(fund_code)


@dependency
def sync_fund_fees(
    fund_code: str | None = None,
    *,
    skip_if_exists: bool = False,
    fund_repo: FundRepo | None = None,
    fund_fee_repo: FundFeeRepo | None = None,
    fund_data_client: FundDataClient | None = None,
) -> SyncFeesResult:
    """
    同步基金费率（从远程数据源抓取）。

    Args:
        fund_code: 基金代码，None 表示同步全部。
        skip_if_exists: 如果已有费率则跳过（用于自动同步场景）。
        fund_repo: 基金仓储（自动注入）。
        fund_fee_repo: 基金费率仓储（自动注入）。
        fund_data_client: 基金数据客户端（自动注入）。

    Returns:
        SyncFeesResult 包含同步统计。

    Raises:
        ValueError: 指定的基金不存在时抛出。
    """
    if fund_code:
        # 同步单只基金
        fund = fund_repo.get(fund_code)
        if fund is None:
            raise ValueError(f"基金不存在：{fund_code}")

        # 已有运作费率则跳过
        if skip_if_exists and fund_fee_repo.has_operating_fees(fund_code):
            return SyncFeesResult(success=0, failed=0, details=[])

        fees_dict = fund_data_client.get_fund_fees(fund_code)
        if fees_dict:
            fees = _build_fund_fees(fees_dict)
            fund_fee_repo.upsert_fees(fund_code, fees)
            return SyncFeesResult(
                success=1,
                failed=0,
                details=[(fund_code, fund.name, True)],
            )
        else:
            return SyncFeesResult(
                success=0,
                failed=1,
                details=[(fund_code, fund.name, False)],
            )
    else:
        # 同步全部基金
        funds = fund_repo.list_all()
        if not funds:
            return SyncFeesResult(success=0, failed=0, details=[])

        success = 0
        failed = 0
        details: list[tuple[str, str, bool]] = []

        for fund in funds:
            fees_dict = fund_data_client.get_fund_fees(fund.fund_code)
            if fees_dict:
                fees = _build_fund_fees(fees_dict)
                fund_fee_repo.upsert_fees(fund.fund_code, fees)
                success += 1
                details.append((fund.fund_code, fund.name, True))
            else:
                failed += 1
                details.append((fund.fund_code, fund.name, False))

        return SyncFeesResult(success=success, failed=failed, details=details)


def _build_fund_fees(fees_dict: dict) -> FundFees:
    """
    从 FundDataClient 返回的 dict 构建 FundFees 对象。

    TODO: 中长期可考虑将 HTML/JS 解析迁移到独立规则模块，
    FundDataClient 只负责 I/O，减少 client 层正则解析逻辑。

    Args:
        fees_dict: FundDataClient.get_fund_fees() 返回的字典。

    Returns:
        FundFees 对象（含赎回费阶梯）。
    """
    # 构建赎回费阶梯
    redemption_tiers: list[RedemptionTier] = []
    if "redemption" in fees_dict and fees_dict["redemption"]:
        for tier_dict in fees_dict["redemption"]:
            tier = RedemptionTier(
                min_hold_days=tier_dict.get("min_hold_days", 0),
                max_hold_days=tier_dict.get("max_hold_days"),
                rate=tier_dict["rate"],
            )
            redemption_tiers.append(tier)

    return FundFees(
        management_fee=fees_dict.get("management_fee"),
        custody_fee=fees_dict.get("custody_fee"),
        service_fee=fees_dict.get("service_fee"),
        purchase_fee=fees_dict.get("purchase_fee"),
        purchase_fee_discount=fees_dict.get("purchase_fee_discount"),
        redemption_tiers=redemption_tiers,
    )
