"""市场数据相关业务流程（净值抓取等）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.core.dependency import dependency
from src.core.log import log
from src.data.client.eastmoney import EastmoneyClient
from src.data.db.calendar import CalendarService
from src.data.db.fund_repo import FundRepo
from src.data.db.nav_repo import NavRepo
from src.data.db.trade_repo import TradeRepo


@dataclass(slots=True)
class FetchNavsResult:
    """
    抓取某一日官方单位净值的结果汇总。

    - day: 目标日期（补抓模式下为 None）；
    - total: 参与抓取的基金数量；
    - success: 成功写入的数量；
    - failed_codes: 获取失败或无效 NAV（None/<=0）的基金代码列表。
    """

    day: date | None
    total: int
    success: int
    failed_codes: list[str]


@dependency
def fetch_navs(
    *,
    day: date | None = None,
    fund_codes: list[str] | None = None,
    fund_repo: FundRepo | None = None,
    nav_repo: NavRepo | None = None,
    eastmoney_service: EastmoneyClient | None = None,
    calendar_service: CalendarService | None = None,
) -> FetchNavsResult:
    """
    按指定日期抓取基金净值并落库。

    口径：
    - 仅抓取"指定日"的官方单位净值（严格版，不做回退）；
    - 成功条件：provider 返回 Decimal 且 > 0；否则视为失败；
    - 落库：调用 NavRepo.upsert(fund_code, day, nav)，按 (fund_code, day) 幂等。

    Args:
        day: 目标日期，None 时使用上一交易日。
        fund_codes: 指定基金代码列表（可选，未指定时抓取所有已配置基金）。
        fund_repo: 基金仓储（自动注入）。
        nav_repo: 净值仓储（自动注入）。
        eastmoney_service: 东方财富服务（自动注入）。
        calendar_service: 交易日历服务（自动注入）。

    Returns:
        抓取结果统计。

    Raises:
        RuntimeError: 日历数据缺失时。
    """
    # 所有依赖已通过装饰器自动注入

    # 默认使用上一交易日
    if day is None:
        prev_day = calendar_service.prev_open("CN_A", date.today(), lookback=15)
        if prev_day is None:
            raise RuntimeError("未能找到上一交易日（15天内），请检查 trading_calendar 表数据")
        day = prev_day

    # 确定要抓取的基金列表
    if fund_codes:
        # 指定基金代码时，从 fund_repo 查询对应的基金信息
        funds = []
        for code in fund_codes:
            fund = fund_repo.get(code)
            if fund:
                funds.append(fund)
            else:
                # 基金代码不存在，记录到失败列表
                log(f"[FetchNavs] ⚠️ 基金代码 {code} 未在系统中配置，跳过")
    else:
        # 未指定时抓取所有基金
        funds = fund_repo.list_all()

    total = len(funds)
    success = 0
    failed_codes: list[str] = []

    for f in funds:
        code = f.fund_code
        nav = eastmoney_service.get_nav(code, day)
        if nav is None or nav <= Decimal("0"):
            failed_codes.append(code)
            continue
        nav_repo.upsert(code, day, nav)
        success += 1

    return FetchNavsResult(day=day, total=total, success=success, failed_codes=failed_codes)


@dependency
def fetch_missing_navs(
    *,
    days: int = 30,
    trade_repo: TradeRepo | None = None,
    nav_repo: NavRepo | None = None,
    eastmoney_service: EastmoneyClient | None = None,
) -> FetchNavsResult:
    """
    自动检测延迟交易的缺失 NAV 并补抓。

    逻辑：
    1. 扫描最近 N 天的延迟交易（confirmation_status='delayed'）
    2. 提取 pricing_date 和 fund_code
    3. 检查 navs 表，找出缺失的 (fund_code, pricing_date)
    4. 批量补抓这些缺失的 NAV

    Args:
        days: 检测最近 N 天的延迟交易，默认 30 天。
        trade_repo: 交易仓储（自动注入）。
        nav_repo: 净值仓储（自动注入）。
        eastmoney_service: 东方财富服务（自动注入）。

    Returns:
        抓取结果统计（day 为 None，total 为缺失 NAV 的总数）。
    """
    # 所有依赖已通过装饰器自动注入

    # 1. 扫描延迟交易
    delayed_trades = trade_repo.list_delayed_trades(days=days)

    if not delayed_trades:
        log("[FetchNavs] 未发现延迟交易，无需补抓 NAV")
        return FetchNavsResult(day=None, total=0, success=0, failed_codes=[])

    # 2. 提取缺失 NAV 的 (fund_code, pricing_date)
    missing_navs: set[tuple[str, date]] = set()
    for t in delayed_trades:
        if t.pricing_date and not nav_repo.exists(t.fund_code, t.pricing_date):
            missing_navs.add((t.fund_code, t.pricing_date))

    if not missing_navs:
        log(f"[FetchNavs] 扫描到 {len(delayed_trades)} 笔延迟交易，但所有 NAV 已存在，无需补抓")
        return FetchNavsResult(day=None, total=0, success=0, failed_codes=[])

    log(f"[FetchNavs] 检测到 {len(missing_navs)} 个缺失 NAV，开始补抓...")

    # 3. 批量补抓
    total = len(missing_navs)
    success = 0
    failed_codes: list[str] = []

    for fund_code, pricing_date in sorted(missing_navs):
        nav = eastmoney_service.get_nav(fund_code, pricing_date)
        if nav is None or nav <= Decimal("0"):
            failed_codes.append(f"{fund_code}@{pricing_date}")
            log(f"[FetchNavs] 补抓失败：{fund_code} {pricing_date}")
            continue
        nav_repo.upsert(fund_code, pricing_date, nav)
        success += 1
        log(f"[FetchNavs] 补抓成功：{fund_code} {pricing_date} = {nav}")

    log(f"[FetchNavs] 补抓完成：total={total} success={success} failed={len(failed_codes)}")
    return FetchNavsResult(day=None, total=total, success=success, failed_codes=failed_codes)
