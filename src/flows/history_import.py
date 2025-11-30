"""历史账单导入业务流程。

v0.4.2 新增：支持从支付宝等平台导入历史基金交易。
详细设计见 docs/history-import.md
"""

from __future__ import annotations

import csv
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from src.core.dependency import dependency
from src.core.models.history_import import (
    ImportRecord,
    ImportResult,
    ImportSource,
)
from src.core.models.trade import TradeStatus, TradeType
from src.data.client.eastmoney import EastmoneyNavService
from src.data.db.action_repo import ActionRepo
from src.data.db.fund_repo import FundRepo
from src.data.db.nav_repo import NavRepo
from src.data.db.trade_repo import TradeRepo

# 支付宝 CSV 常量
_ALIPAY_ENCODING = "gbk"
_ALIPAY_SKIP_ROWS = 5
_ALIPAY_FUND_COUNTERPARTY = "蚂蚁财富-蚂蚁（杭州）基金销售有限公司"
_ALIPAY_FUND_STATUS = "资金转移"

# 商品名称正则：蚂蚁财富-{基金名称}-{买入/卖出}
_ALIPAY_PRODUCT_PATTERN = re.compile(r"^蚂蚁财富-(.+)-(买入|卖出)$")

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

    Args:
        csv_path: CSV 文件路径。
        source: 来源平台。

    Returns:
        解析后的 ImportRecord 列表。
    """
    if source == "alipay":
        return _parse_alipay_csv(csv_path)
    # ttjj 等其他平台预留
    raise ValueError(f"不支持的导入来源：{source}")


def _parse_alipay_csv(csv_path: str) -> list[ImportRecord]:
    """
    解析支付宝账单 CSV。

    CSV 列结构（16 列）：
    0: 交易号, 2: 交易创建时间, 7: 交易对方, 8: 商品名称,
    9: 金额（元）, 11: 交易状态, 15: 资金状态
    """
    records: list[ImportRecord] = []

    with open(csv_path, encoding=_ALIPAY_ENCODING, newline="") as f:
        # 跳过头部行
        for _ in range(_ALIPAY_SKIP_ROWS):
            f.readline()

        reader = csv.reader(f)
        for row_num, row in enumerate(reader, start=_ALIPAY_SKIP_ROWS + 1):
            # 跳过空行或列数不足的行
            if len(row) < 16:
                continue

            # 清理每列首尾空白和制表符
            row = [col.strip() for col in row]

            # 过滤基金交易：交易对方 + 资金状态
            counterparty = row[7]
            fund_status = row[15]
            if counterparty != _ALIPAY_FUND_COUNTERPARTY:
                continue
            if fund_status != _ALIPAY_FUND_STATUS:
                continue

            # 解析交易状态，跳过"交易关闭"
            alipay_status = row[11]
            target_status = _map_alipay_status(alipay_status)
            if target_status is None:
                continue  # 交易关闭，跳过

            # 解析商品名称 → 基金名称 + 交易类型
            product_name = row[8]
            parsed = _parse_alipay_product(product_name)
            if parsed is None:
                # 商品名称格式异常，创建错误记录
                records.append(
                    ImportRecord(
                        source="alipay",
                        external_id=row[0],
                        original_fund_name=product_name,
                        trade_type="buy",  # 占位
                        trade_time=datetime.now(),  # 占位
                        amount=Decimal("0"),
                        target_status="pending",
                        error_type="parse_error",
                        error_message=f"商品名称格式异常：{product_name}",
                    )
                )
                continue

            fund_name, trade_type = parsed

            # 解析交易时间
            try:
                trade_time = datetime.strptime(row[2], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                records.append(
                    ImportRecord(
                        source="alipay",
                        external_id=row[0],
                        original_fund_name=fund_name,
                        trade_type=trade_type,
                        trade_time=datetime.now(),
                        amount=Decimal("0"),
                        target_status=target_status,
                        error_type="parse_error",
                        error_message=f"交易时间格式异常：{row[2]}",
                    )
                )
                continue

            # 解析金额
            try:
                amount = Decimal(row[9])
                if amount <= 0:
                    raise InvalidOperation("金额必须为正数")
            except InvalidOperation:
                records.append(
                    ImportRecord(
                        source="alipay",
                        external_id=row[0],
                        original_fund_name=fund_name,
                        trade_type=trade_type,
                        trade_time=trade_time,
                        amount=Decimal("0"),
                        target_status=target_status,
                        error_type="invalid_data",
                        error_message=f"金额异常：{row[9]}",
                    )
                )
                continue

            # 创建有效记录
            records.append(
                ImportRecord(
                    source="alipay",
                    external_id=row[0],
                    original_fund_name=fund_name,
                    trade_type=trade_type,
                    trade_time=trade_time,
                    amount=amount,
                    target_status=target_status,
                )
            )

    return records


def _map_alipay_status(alipay_status: str) -> TradeStatus | None:
    """
    映射支付宝交易状态到 TradeStatus。

    Returns:
        TradeStatus 或 None（交易关闭时返回 None 表示跳过）。
    """
    if alipay_status == "交易成功":
        return "confirmed"
    if alipay_status == "付款成功，份额确认中":
        return "pending"
    # 交易关闭或其他状态 → 跳过
    return None


def _parse_alipay_product(product_name: str) -> tuple[str, TradeType] | None:
    """
    解析支付宝商品名称。

    格式：蚂蚁财富-{基金名称}-{买入/卖出}

    Returns:
        (基金名称, 交易类型) 或 None（格式异常）。
    """
    match = _ALIPAY_PRODUCT_PATTERN.match(product_name)
    if not match:
        return None
    fund_name = match.group(1)
    trade_type: TradeType = "buy" if match.group(2) == "买入" else "sell"
    return fund_name, trade_type


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
