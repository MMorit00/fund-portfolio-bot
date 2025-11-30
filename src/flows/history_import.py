"""历史账单导入业务流程。

v0.4.2 新增：支持从支付宝等平台导入历史基金交易。
详细设计见 docs/history-import.md

当前状态：骨架实现，核心逻辑待完成。
"""

from __future__ import annotations

from typing import Literal

from src.core.dependency import dependency
from src.core.models.history_import import (
    ImportRecord,
    ImportResult,
    ImportSource,
)
from src.data.client.eastmoney import EastmoneyNavService
from src.data.db.action_repo import ActionRepo
from src.data.db.fund_repo import FundRepo
from src.data.db.nav_repo import NavRepo
from src.data.db.trade_repo import TradeRepo

# 导入模式
ImportMode = Literal["dry_run", "apply"]


@dependency
def import_trades_from_csv(
    *,
    csv_path: str,
    source: ImportSource = "alipay",
    mode: ImportMode = "dry_run",
    with_actions: bool = True,
    fund_repo: FundRepo | None = None,
    trade_repo: TradeRepo | None = None,
    nav_repo: NavRepo | None = None,
    action_repo: ActionRepo | None = None,
    eastmoney_service: EastmoneyNavService | None = None,
) -> ImportResult:
    """
    从 CSV 文件导入历史交易。

    导入流程：
    1. 解析 CSV（GBK 编码）→ 过滤基金交易 → 生成 ImportRecord
    2. 映射 fund_code + market（通过 funds.alias 查询）
    3. 抓取历史 NAV（通过 EastmoneyNavService）
    4. 计算份额（amount / nav）
    5. 写入 trades 表（mode=apply 时）
    6. 补录 action_log（with_actions=True 时）

    状态映射（支付宝 → Trade.status）：
    - "交易成功" → confirmed（直接写入确认后的交易）
    - "付款成功，份额确认中" → pending（等待后续确认）
    - "交易关闭" → 跳过

    Args:
        csv_path: CSV 文件路径。
        source: 来源平台（alipay / ttjj）。
        mode: 导入模式（dry_run=只校验 / apply=实际写入）。
        with_actions: 是否同时补录 ActionLog。
        fund_repo: 基金仓储（自动注入）。
        trade_repo: 交易仓储（自动注入）。
        nav_repo: 净值仓储（自动注入）。
        action_repo: 行为日志仓储（自动注入）。
        eastmoney_service: 东方财富服务（自动注入）。

    Returns:
        ImportResult: 导入结果统计。

    Raises:
        NotImplementedError: 当前版本未实现。

    Example:
        >>> # 干跑模式（只检查，不写入）
        >>> result = import_trades_from_csv(csv_path="data/alipay.csv", mode="dry_run")
        >>> print(f"识别 {result.total} 笔，可导入 {result.succeeded} 笔")

        >>> # 实际导入
        >>> result = import_trades_from_csv(csv_path="data/alipay.csv", mode="apply")
        >>> print(f"成功导入 {result.succeeded} 笔，失败 {result.failed} 笔")
    """
    # TODO: 实现具体逻辑
    #
    # 步骤 1: records = _parse_csv(csv_path, source)
    # 步骤 2: _map_funds(records, fund_repo)
    # 步骤 3: _fetch_navs(records, eastmoney_service, nav_repo)
    # 步骤 4: _calculate_shares(records)
    # 步骤 5: if mode == "apply": _write_trades(records, trade_repo, action_repo)
    # 步骤 6: return _build_result(records)

    raise NotImplementedError(
        "历史账单导入目前处于规划阶段，仅完成接口与文档设计。\n"
        "详见 docs/history-import.md"
    )


def _parse_csv(csv_path: str, source: ImportSource) -> list[ImportRecord]:
    """
    解析 CSV 文件，过滤基金交易，生成 ImportRecord 列表。

    解析规则（支付宝）：
    - 编码：GBK
    - 跳过前 5 行头部
    - 基金特征：交易对方="蚂蚁财富-..." 且 资金状态="资金转移"
    - 从商品名称解析：基金名称 + 交易类型（买入/卖出）
    - 状态映射：交易成功→confirmed，份额确认中→pending，交易关闭→跳过

    TODO: 实现解析逻辑
    """
    raise NotImplementedError


def _map_funds(records: list[ImportRecord], fund_repo: FundRepo) -> None:
    """
    映射 fund_code 和 market。

    逻辑：
    1. 根据 original_fund_name 查询 funds.alias
    2. 找到匹配的 fund_code 和 market
    3. 映射失败的记录标记 error_type="fund_not_found"

    TODO: 实现映射逻辑（需先实现 FundRepo.find_by_alias）
    """
    raise NotImplementedError


def _fetch_navs(
    records: list[ImportRecord],
    eastmoney_service: EastmoneyNavService,
    nav_repo: NavRepo,
) -> None:
    """
    批量抓取历史 NAV。

    逻辑：
    1. 对每条有效记录，调用 eastmoney_service.get_nav(fund_code, trade_date)
    2. 抓取成功则填充 record.nav
    3. 抓取失败且 target_status="confirmed" 则标记 error_type="nav_missing"
    4. 抓取失败且 target_status="pending" 则跳过（后续正常确认流程处理）

    优化：先查 nav_repo 缓存，避免重复抓取

    TODO: 实现抓取逻辑
    """
    raise NotImplementedError


def _calculate_shares(records: list[ImportRecord]) -> None:
    """
    计算份额 = amount / nav。

    逻辑：
    - 只对有 nav 的记录计算
    - 保留 4 位小数

    TODO: 实现计算逻辑
    """
    raise NotImplementedError


def _write_trades(
    records: list[ImportRecord],
    trade_repo: TradeRepo,
    action_repo: ActionRepo | None,
    with_actions: bool,
) -> int:
    """
    写入 trades 表（+ 可选 action_log）。

    逻辑：
    1. 过滤 is_valid 的记录
    2. 构造 Trade 对象，写入 trade_repo
    3. 如果 with_actions=True，补录 action_log

    TODO: 实现写入逻辑
    """
    raise NotImplementedError


def _build_result(records: list[ImportRecord]) -> ImportResult:
    """
    根据处理后的 records 构建 ImportResult。

    TODO: 实现统计逻辑
    """
    raise NotImplementedError
