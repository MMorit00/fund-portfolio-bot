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
from src.core.log import log
from src.core.models import (
    AssetClass,
    ImportRecord,
    ImportResult,
    ImportSource,
    MarketType,
    TradeStatus,
    TradeType,
)
from src.core.rules.precision import quantize_shares
from src.core.rules.settlement import calc_pricing_date, default_policy
from src.data.client.eastmoney import EastmoneyClient
from src.data.db.action_repo import ActionRepo
from src.data.db.calendar import CalendarService
from src.data.db.fund_repo import FundRepo
from src.data.db.nav_repo import NavRepo
from src.data.db.trade_repo import TradeRepo
from src.flows.fund_fees import sync_fund_fees

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
    eastmoney_service: EastmoneyClient | None = None,
    calendar_service: CalendarService | None = None,
) -> ImportResult:
    """
    从 CSV 文件导入历史交易。

    导入流程：
    1. 解析 CSV（GBK 编码）→ 过滤基金交易 → 生成 ImportRecord
    2. 映射 fund_code + market（通过 funds.alias 查询）
    3. 抓取历史 NAV（通过 EastmoneyClient）
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
        calendar_service: 日历服务（自动注入，用于计算定价日）。

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
    # 步骤 1: 解析 CSV
    records = _parse_csv(csv_path, source)

    # 步骤 2: 自动解析基金（仅 apply 模式，v0.4.2 修复）
    # 原因：dry-run 不应写入数据库，apply 时才自动创建基金记录
    if mode == "apply" and fund_repo is not None and eastmoney_service is not None:
        _auto_resolve_funds(records, fund_repo, eastmoney_service)

    # 步骤 3: 映射 fund_code + market
    if fund_repo is not None:
        _map_funds(records, fund_repo)

    # 步骤 4: 抓取历史 NAV（使用定价日而非下单日）
    if eastmoney_service is not None and nav_repo is not None and calendar_service is not None:
        _fetch_navs(records, eastmoney_service, nav_repo, calendar_service)

    # 步骤 5: 计算份额
    _calculate_shares(records)

    # 步骤 6: 去重检查（标记已存在的记录）
    if trade_repo is not None:
        _check_duplicates(records, trade_repo)

    # 步骤 7: 写入数据库（apply 模式）
    succeeded = 0
    if mode == "apply" and trade_repo is not None:
        succeeded = _write_trades(
            records, trade_repo, action_repo, with_actions, csv_path
        )
    elif mode == "dry_run":
        # dry_run 模式：统计可导入数量（不实际写入）
        for record in records:
            if record.error_type == "duplicate":
                continue  # 跳过重复记录
            if record.target_status == "confirmed":
                if record.can_confirm:
                    succeeded += 1
            elif record.is_valid:
                succeeded += 1

    # 步骤 7: 构建结果
    return _build_result(records, succeeded, fund_repo)


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
                        raw_fund_name=product_name,
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
                        raw_fund_name=fund_name,
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
                        raw_fund_name=fund_name,
                        trade_type=trade_type,
                        trade_time=trade_time,
                        amount=Decimal("0"),
                        target_status=target_status,
                        error_type="invalid_data",
                        error_message=f"金额异常：{row[9]}",
                    )
                )
                continue

            # 创建有效记录（使用支付宝订单号作为 external_id）
            records.append(
                ImportRecord(
                    source="alipay",
                    external_id=row[0],  # 支付宝订单号
                    raw_fund_name=fund_name,
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


def _auto_resolve_funds(
    records: list[ImportRecord],
    fund_repo: FundRepo,
    eastmoney_client: EastmoneyClient,
) -> None:
    """
    自动解析并创建基金记录。

    流程：
    1. 收集所有唯一的基金名称
    2. 跳过已存在的基金（通过外部名称查询）
    3. 调用东方财富 API 搜索未知基金
    4. 自动创建 funds 表记录（含外部名称用于后续匹配）

    Args:
        records: ImportRecord 列表。
        fund_repo: 基金仓储。
        eastmoney_client: 东方财富客户端。

    副作用：
        首次遇到新基金时，自动创建 funds 表记录。
        解析失败的基金会在后续 _map_funds 中被标记为 error。
    """

    # 收集所有唯一的基金名称
    unique_fund_names = {
        record.raw_fund_name
        for record in records
        if record.error_type is None
    }

    if not unique_fund_names:
        return

    log(f"[Flow:HistoryImport] 自动解析基金（共 {len(unique_fund_names)} 只）...")

    resolved_count = 0
    for fund_name in unique_fund_names:
        # 步骤 1: 检查本地是否已存在
        if fund_repo.find_by_external_name(fund_name) is not None:
            resolved_count += 1
            continue

        # 步骤 2: 调用东方财富搜索 API
        search_result = eastmoney_client.search_fund(fund_name)
        if search_result is None:
            log(f"[Flow:HistoryImport] 未找到匹配基金：{fund_name}")
            continue

        # 步骤 3: 创建基金记录
        fund_code = search_result["fund_code"]
        name = search_result["name"]
        market = search_result["market"]
        asset_class = _infer_asset_class(search_result)

        log(f"[Flow:HistoryImport] 创建基金：{fund_name} → {fund_code} ({asset_class.value})")
        fund_repo.add(fund_code, name, asset_class, market, external_name=fund_name)

        # 自动抓取费率（v0.4.3 新增）
        sync_fund_fees(fund_code)

        resolved_count += 1

    log(f"[Flow:HistoryImport] 成功解析 {resolved_count}/{len(unique_fund_names)} 只基金")


def _infer_asset_class(fund_info: dict) -> AssetClass:
    """
    根据基金信息推断 asset_class。

    推断规则：
    1. 债券型 → CGB_3_5Y
    2. QDII/海外 → US_QDII
    3. 其他 → CSI300（默认）

    Args:
        fund_info: search_fund() 返回的基金信息字典。

    Returns:
        AssetClass 枚举值。
    """
    ftype = fund_info.get("ftype", "")
    name = fund_info.get("name", "")
    market = fund_info.get("market", "CN_A")

    # 规则 1：债券型
    if "债券" in ftype or "债" in ftype:
        return AssetClass.CGB_3_5Y

    # 规则 2：QDII/海外
    if market == "US_NYSE" or "QDII" in ftype or "QDII" in name or "海外" in ftype:
        return AssetClass.US_QDII

    # 规则 3：默认
    return AssetClass.CSI300


def _map_funds(records: list[ImportRecord], fund_repo: FundRepo) -> None:
    """
    映射 fund_code 和 market。

    逻辑：
    1. 根据 raw_fund_name 查询外部名称映射（当前使用 funds.alias 字段）
    2. 找到匹配的 fund_code 和 market
    3. 映射失败的记录标记 error_type="fund_not_found"

    TODO: 将外部名称映射迁移到独立的 FundNameMapping 仓储，避免 ImportRecord
    直接依赖 funds.alias 字段。

    Args:
        records: ImportRecord 列表（原地修改）。
        fund_repo: 基金仓储。
    """
    # 缓存已查询的映射结果，避免重复查询
    external_name_cache: dict[str, tuple[str, str] | None] = {}

    for record in records:
        # 跳过已有错误的记录
        if record.error_type is not None:
            continue

        fund_name = record.raw_fund_name

        # 查缓存
        if fund_name in external_name_cache:
            cached = external_name_cache[fund_name]
            if cached is None:
                record.error_type = "fund_not_found"
                record.error_message = f"未找到基金外部名称映射：{fund_name}"
            else:
                record.fund_code, record.market = cached
            continue

        # 查数据库
        fund_info = fund_repo.find_by_external_name(fund_name)
        if fund_info is None:
            external_name_cache[fund_name] = None
            record.error_type = "fund_not_found"
            record.error_message = f"未找到基金外部名称映射：{fund_name}"
        else:
            external_name_cache[fund_name] = (fund_info.fund_code, fund_info.market)
            record.fund_code = fund_info.fund_code
            record.market = fund_info.market


def _fetch_navs(
    records: list[ImportRecord],
    eastmoney_client: EastmoneyClient,
    nav_repo: NavRepo,
    calendar_service: CalendarService,
) -> None:
    """
    批量抓取历史 NAV。

    重要：使用 **定价日（pricing_date）** 而非下单日（trade_date）抓取 NAV。

    原因：支付宝允许 7×24 下单，但基金公司只在开放日处理，按定价日净值计算份额。
    例如：周六下单 → 定价日是下周一 → 使用周一的 NAV。

    逻辑：
    1. 根据 market 获取结算策略，计算 pricing_date
    2. 调用 eastmoney_client.get_nav(fund_code, pricing_date)
    3. 抓取成功则填充 record.nav
    4. 抓取失败且 target_status="confirmed" 则标记 error_type="nav_missing"
    5. 抓取失败且 target_status="pending" 则跳过（后续正常确认流程处理）

    优化：先查 nav_repo 缓存，避免重复抓取

    Args:
        records: ImportRecord 列表（原地修改）。
        eastmoney_client: 东方财富客户端。
        nav_repo: 净值仓储（缓存查询）。
        calendar_service: 日历服务（用于计算定价日）。
    """
    # 缓存：(fund_code, pricing_date) → nav
    nav_cache: dict[tuple[str, str], Decimal | None] = {}

    for record in records:
        # 跳过已有错误或未完成映射的记录
        if record.error_type is not None or record.fund_code is None or record.market is None:
            continue

        fund_code = record.fund_code
        market: MarketType = record.market

        # 计算定价日（关键修复：使用 pricing_date 而非 trade_date）
        try:
            policy = default_policy(market)
            pricing_date = calc_pricing_date(record.trade_date, policy, calendar_service)
        except (ValueError, RuntimeError) as e:
            # 日历数据缺失等错误
            if record.target_status == "confirmed":
                record.error_type = "nav_missing"
                record.error_message = f"无法计算定价日：{e}"
            continue

        cache_key = (fund_code, str(pricing_date))

        # 查缓存
        if cache_key in nav_cache:
            nav = nav_cache[cache_key]
        else:
            # 先查 nav_repo（本地数据库缓存）
            nav = nav_repo.get(fund_code, pricing_date)
            if nav is None:
                # 调用东方财富 API
                nav = eastmoney_client.get_nav(fund_code, pricing_date)
                # 如果抓取成功，存入本地缓存
                if nav is not None:
                    nav_repo.upsert(fund_code, pricing_date, nav)
            nav_cache[cache_key] = nav

        if nav is not None:
            record.nav = nav
        elif record.target_status == "confirmed":
            # confirmed + NAV 缺失 → 自动降级为 pending（v0.4.2+ 优化）
            # 原因：支付宝显示"交易成功"，但暂时拿不到净值时，不应拒绝导入
            # 策略：降级为 pending，后续通过 confirm_trades 正常流程自动确认
            record.target_status = "pending"
            record.was_downgraded = True  # 标记降级（v0.4.2+）
            log(f"[Flow:HistoryImport] NAV 暂缺，降级为 pending：{fund_code} @ {pricing_date}")
        # pending 记录不需要 NAV（后续正常确认流程处理）


def _calculate_shares(records: list[ImportRecord]) -> None:
    """
    计算份额 = amount / nav。

    逻辑：
    - 只对有 nav 的记录计算
    - 保留 4 位小数（ROUND_HALF_UP）

    Args:
        records: ImportRecord 列表（原地修改）。
    """
    for record in records:
        # 跳过无 NAV 的记录
        if record.nav is None:
            continue

        # 计算份额，统一使用精度工具函数
        record.shares = quantize_shares(record.amount / record.nav)


def _check_duplicates(records: list[ImportRecord], trade_repo: TradeRepo) -> None:
    """
    检查并标记重复记录（v0.4.2 新增）。

    逻辑：
    1. 维护内存 set 追踪 CSV 内部重复
    2. 遍历所有记录：
       a. 先检查 CSV 内部重复（set）
       b. 再检查数据库重复（trade_repo）
    3. 重复记录标记为 error_type="duplicate"

    Args:
        records: ImportRecord 列表（原地修改）。
        trade_repo: 交易仓储（用于查询已存在的 external_id）。
    """
    duplicate_count = 0
    seen_external_ids: set[str] = set()  # 追踪 CSV 内部已见的 external_id

    for record in records:
        # 跳过已有错误的记录
        if record.error_type is not None:
            continue

        # 跳过无 external_id 的记录
        if not record.external_id:
            continue

        # 检查1：CSV 内部重复
        if record.external_id in seen_external_ids:
            record.error_type = "duplicate"
            record.error_message = f"CSV 内部重复：{record.external_id}"
            duplicate_count += 1
            continue

        # 检查2：数据库重复
        if trade_repo.exists_by_external_id(record.external_id):
            record.error_type = "duplicate"
            record.error_message = f"订单已存在：{record.external_id}"
            duplicate_count += 1
            continue

        # 记录已见 external_id
        seen_external_ids.add(record.external_id)

    if duplicate_count > 0:
        log(f"[Flow:HistoryImport] 检测到 {duplicate_count} 笔重复记录，已跳过")


def _write_trades(
    records: list[ImportRecord],
    trade_repo: TradeRepo,
    action_repo: ActionRepo | None,
    with_actions: bool,
    csv_path: str,
) -> int:
    """
    写入 trades 表（+ 可选 action_log）。

    逻辑：
    1. confirmed 记录：can_confirm（有 NAV + 有份额）
    2. pending 记录：is_valid（有 fund_code + market）
    3. 构造 Trade 对象，写入 trade_repo
    4. 如果 with_actions=True，补录 action_log

    Args:
        records: ImportRecord 列表。
        trade_repo: 交易仓储。
        action_repo: 行为日志仓储（可选）。
        with_actions: 是否补录 ActionLog。
        csv_path: CSV 文件路径（用于 ActionLog.note）。

    Returns:
        成功写入的交易数量。
    """
    from pathlib import Path

    from src.core.models.action import ActionLog
    from src.core.models.trade import Trade

    succeeded = 0
    csv_name = Path(csv_path).name

    for record in records:
        # 跳过重复记录
        if record.error_type == "duplicate":
            continue

        # 判断是否可以写入
        if record.target_status == "confirmed":
            # confirmed 记录需要 can_confirm
            if not record.can_confirm:
                continue
        else:
            # pending 记录只需要 is_valid
            if not record.is_valid:
                continue

        # 构造 Trade 对象（nav 已存入 navs 表，不冗余存储到 trades）
        trade = Trade(
            id=None,
            fund_code=record.fund_code,
            type=record.trade_type,
            amount=record.amount,
            trade_date=record.trade_date,
            status=record.target_status,
            market=record.market,
            shares=record.shares,  # confirmed 有值，pending 为 None
            remark=f"导入自 {record.source}（{csv_name}）",
            external_id=record.external_id,
        )

        # 写入 trades 表
        saved_trade = trade_repo.add(trade)
        succeeded += 1

        # 补录 ActionLog
        if with_actions and action_repo is not None:
            action_log = ActionLog(
                id=None,
                action=record.trade_type,  # buy / sell
                actor="human",
                source="import",
                acted_at=record.trade_time,
                fund_code=record.fund_code,
                target_date=record.trade_date,
                trade_id=saved_trade.id,
                intent="planned",  # 历史行为无法判断，默认 planned
                note=f"导入自{record.source}账单（{csv_name}）",
            )
            action_repo.add(action_log)

    return succeeded


def _build_result(
    records: list[ImportRecord],
    succeeded: int,
    fund_repo: FundRepo | None = None,
) -> ImportResult:
    """
    根据处理后的 records 构建 ImportResult。

    统计逻辑：
    - total: 所有记录数（包括错误记录）
    - succeeded: 成功写入的记录数（由 _write_trades 返回）
    - failed: 有错误的记录数
    - skipped: 重复记录数（error_type="duplicate"）
    - downgraded_count: 因 NAV 缺失降级为 pending 的数量（v0.4.2+）

    Args:
        records: ImportRecord 列表。
        succeeded: 成功写入的交易数量。
        fund_repo: 基金仓储（用于构建映射摘要）。

    Returns:
        ImportResult 统计结果。
    """
    total = len(records)
    failed_records = [r for r in records if r.error_type is not None]
    failed = len(failed_records)
    skipped = len([r for r in failed_records if r.error_type == "duplicate"])

    # 统计降级数量（v0.4.2+ 新增）
    # 注：降级记录不算失败，会成功写入为 pending 状态
    downgraded_count = sum(1 for record in records if record.was_downgraded)

    # 构建基金映射摘要（v0.4.2+ 新增）
    fund_mapping: dict[str, tuple[str, str]] = {}
    if fund_repo is not None:
        seen_names = set()
        for record in records:
            if record.fund_code and record.original_fund_name not in seen_names:
                fund_info = fund_repo.get(record.fund_code)
                if fund_info:
                    fund_mapping[record.original_fund_name] = (
                        record.fund_code,
                        fund_info.name,
                    )
                    seen_names.add(record.original_fund_name)

    # 构建错误分类统计（v0.4.2+ 新增）
    error_summary: dict[str, int] = {}
    for record in failed_records:
        if record.error_type:
            error_summary[record.error_type] = error_summary.get(record.error_type, 0) + 1

    return ImportResult(
        total=total,
        succeeded=succeeded,
        failed=failed - skipped,  # 失败数不含跳过
        skipped=skipped,
        downgraded_count=downgraded_count,
        failed_records=failed_records,
        fund_mapping=fund_mapping,
        error_summary=error_summary,
    )
