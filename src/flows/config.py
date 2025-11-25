from __future__ import annotations

from decimal import Decimal

from src.core.dependency import dependency
from src.core.models.alloc_config import AllocConfig
from src.core.models.asset_class import AssetClass
from src.core.models.dca_plan import DcaPlan
from src.core.models.fund import FundInfo
from src.data.db.alloc_config_repo import AllocConfigRepo
from src.data.db.dca_plan_repo import DcaPlanRepo
from src.data.db.fund_repo import FundRepo

# ==================== 基金管理 ====================


@dependency
def add_fund(
    *,
    fund_code: str,
    name: str,
    asset_class: AssetClass,
    market: str,
    fund_repo: FundRepo | None = None,
) -> None:
    """
    添加或更新基金信息（v0.3.2）。

    Args:
        fund_code: 基金代码（6 位数字）。
        name: 基金名称。
        asset_class: 资产类别（AssetClass 枚举）。
        market: 市场类型（CN_A/US_NYSE 等）。
        fund_repo: 基金仓储（可选，自动注入）。

    副作用：
        幂等插入或更新 funds 表。
    """
    fund_repo.add(fund_code, name, asset_class, market)


@dependency
def list_funds(
    *,
    fund_repo: FundRepo | None = None,
) -> list[FundInfo]:
    """
    查询所有基金（v0.3.2）。

    Args:
        fund_repo: 基金仓储（可选，自动注入）。

    Returns:
        所有基金列表，按 fund_code 排序。
    """
    return fund_repo.list_all()


@dependency
def remove_fund(
    *,
    fund_code: str,
    fund_repo: FundRepo | None = None,
) -> None:
    """
    删除基金（v0.3.4 新增）。

    Args:
        fund_code: 基金代码。
        fund_repo: 基金仓储（可选，自动注入）。

    Raises:
        ValueError: 基金不存在时抛出。

    副作用：
        从 funds 表删除指定基金。
    """
    fund_repo.delete(fund_code)


# ==================== 定投计划管理 ====================


@dependency
def add_dca_plan(
    *,
    fund_code: str,
    amount: Decimal,
    frequency: str,
    rule: str,
    status: str = "active",
    dca_plan_repo: DcaPlanRepo | None = None,
) -> None:
    """
    添加或更新定投计划（v0.3.2）。

    Args:
        fund_code: 基金代码。
        amount: 定投金额（Decimal）。
        frequency: 频率（daily/weekly/monthly）。
        rule: 规则（对应频率的具体日期/星期）。
        status: 状态（active/disabled），默认 active。
        dca_plan_repo: 定投计划仓储（可选，自动注入）。

    副作用:
        幂等插入或更新 dca_plans 表。
    """
    dca_plan_repo.upsert(fund_code, amount, frequency, rule, status)


@dependency
def list_dca_plans(
    *,
    active_only: bool = False,
    dca_plan_repo: DcaPlanRepo | None = None,
) -> list[DcaPlan]:
    """
    查询定投计划（v0.3.2）。

    Args:
        active_only: 是否仅返回活跃计划，默认 False（返回全部）。
        dca_plan_repo: 定投计划仓储（可选，自动注入）。

    Returns:
        定投计划列表，按 fund_code 排序。
    """
    if active_only:
        return dca_plan_repo.list_active()
    return dca_plan_repo.list_all()


@dependency
def disable_dca_plan(
    *,
    fund_code: str,
    dca_plan_repo: DcaPlanRepo | None = None,
) -> None:
    """
    禁用定投计划（v0.3.2）。

    Args:
        fund_code: 基金代码。
        dca_plan_repo: 定投计划仓储（可选，自动注入）。

    Raises:
        ValueError: 计划不存在时抛出。

    副作用：
        更新 dca_plans 表的 status 字段为 'disabled'。
    """
    dca_plan_repo.set_status(fund_code, "disabled")


@dependency
def enable_dca_plan(
    *,
    fund_code: str,
    dca_plan_repo: DcaPlanRepo | None = None,
) -> None:
    """
    启用定投计划（v0.3.2）。

    Args:
        fund_code: 基金代码。
        dca_plan_repo: 定投计划仓储（可选，自动注入）。

    Raises:
        ValueError: 计划不存在时抛出。

    副作用：
        更新 dca_plans 表的 status 字段为 'active'。
    """
    dca_plan_repo.set_status(fund_code, "active")


@dependency
def delete_dca_plan(
    *,
    fund_code: str,
    dca_plan_repo: DcaPlanRepo | None = None,
) -> None:
    """
    删除定投计划（v0.3.4 新增）。

    Args:
        fund_code: 基金代码。
        dca_plan_repo: 定投计划仓储（可选，自动注入）。

    Raises:
        ValueError: 计划不存在时抛出。

    副作用：
        从 dca_plans 表删除指定计划。
    """
    dca_plan_repo.delete(fund_code)


# ==================== 资产配置管理 ====================


@dependency
def set_allocation(
    *,
    asset_class: AssetClass,
    target_weight: Decimal,
    max_deviation: Decimal,
    alloc_config_repo: AllocConfigRepo | None = None,
) -> None:
    """
    设置资产配置目标（v0.3.2）。

    Args:
        asset_class: 资产类别（AssetClass 枚举）。
        target_weight: 目标权重（0..1，Decimal）。
        max_deviation: 允许的最大偏离（0..1，Decimal）。
        alloc_config_repo: 配置仓储（可选，自动注入）。

    副作用：
        幂等插入或更新 alloc_config 表。
    """
    alloc_config_repo.set_alloc(asset_class, target_weight, max_deviation)


@dependency
def list_allocations(
    *,
    alloc_config_repo: AllocConfigRepo | None = None,
) -> list[AllocConfig]:
    """
    查询所有资产配置目标（v0.3.2）。

    Args:
        alloc_config_repo: 配置仓储（可选，自动注入）。

    Returns:
        所有资产配置列表，按 asset_class 排序。
    """
    return alloc_config_repo.list_all()


@dependency
def delete_allocation(
    *,
    asset_class: AssetClass,
    alloc_config_repo: AllocConfigRepo | None = None,
) -> None:
    """
    删除资产配置目标（v0.3.4 新增）。

    Args:
        asset_class: 资产类别（AssetClass 枚举）。
        alloc_config_repo: 配置仓储（可选，自动注入）。

    Raises:
        ValueError: 配置不存在时抛出。

    副作用：
        从 alloc_config 表删除指定资产配置。
    """
    alloc_config_repo.delete(asset_class)
