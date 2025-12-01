"""基金费率管理（v0.4.3）"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.dependency import dependency
from src.core.models.fund import FundFees, FundInfo
from src.data.client.eastmoney import EastmoneyClient
from src.data.db.fund_repo import FundRepo


@dataclass(slots=True)
class SyncFeesResult:
    """费率同步结果。"""

    success: int
    failed: int
    details: list[tuple[str, str, bool]]  # (fund_code, name, success)


@dependency
def get_fund_fees(
    fund_code: str,
    *,
    fund_repo: FundRepo | None = None,
) -> FundInfo | None:
    """
    获取基金费率信息。

    Args:
        fund_code: 基金代码。
        fund_repo: 基金仓储（自动注入）。

    Returns:
        FundInfo（含费率字段）或 None（基金不存在）。
    """
    return fund_repo.get(fund_code)


@dependency
def sync_fund_fees(
    fund_code: str | None = None,
    *,
    skip_if_exists: bool = False,
    fund_repo: FundRepo | None = None,
    eastmoney_service: EastmoneyClient | None = None,
) -> SyncFeesResult:
    """
    同步基金费率（从东方财富抓取）。

    Args:
        fund_code: 基金代码，None 表示同步全部。
        skip_if_exists: 如果已有费率则跳过（用于自动同步场景）。
        fund_repo: 基金仓储（自动注入）。
        eastmoney_service: 东方财富客户端（自动注入）。

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
        if skip_if_exists and (fund.management_fee is not None or fund.custody_fee is not None):
            return SyncFeesResult(success=0, failed=0, details=[])

        fees_dict = eastmoney_service.get_fund_fees(fund_code)
        if fees_dict:
            fees = FundFees(
                management_fee=fees_dict.get("management_fee"),
                custody_fee=fees_dict.get("custody_fee"),
                service_fee=fees_dict.get("service_fee"),
                purchase_fee=fees_dict.get("purchase_fee"),
                purchase_fee_discount=fees_dict.get("purchase_fee_discount"),
            )
            fund_repo.update_fees(fund_code, fees)
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
            fees_dict = eastmoney_service.get_fund_fees(fund.fund_code)
            if fees_dict:
                fees = FundFees(
                    management_fee=fees_dict.get("management_fee"),
                    custody_fee=fees_dict.get("custody_fee"),
                    service_fee=fees_dict.get("service_fee"),
                    purchase_fee=fees_dict.get("purchase_fee"),
                    purchase_fee_discount=fees_dict.get("purchase_fee_discount"),
                )
                fund_repo.update_fees(fund.fund_code, fees)
                success += 1
                details.append((fund.fund_code, fund.name, True))
            else:
                failed += 1
                details.append((fund.fund_code, fund.name, False))

        return SyncFeesResult(success=success, failed=failed, details=details)
