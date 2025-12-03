"""持仓市值计算功能（v0.4.2+）"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.core.dependency import dependency
from src.data.client.eastmoney import EastmoneyClient
from src.data.db.calendar import CalendarService
from src.data.db.fund_repo import FundRepo
from src.data.db.nav_repo import NavRepo
from src.data.db.trade_repo import TradeRepo


@dataclass(slots=True)
class FundHolding:
    """基金持仓（用于市值计算与对账）。"""

    fund_code: str
    fund_name: str
    shares: Decimal
    nav: Decimal | None = None
    nav_source: str = "缺失"  # "官方" / "估值" / "缺失"
    estimated_time: str | None = None
    market_value: Decimal | None = None


@dataclass(slots=True)
class MarketValueResult:
    """持仓市值计算结果。"""

    as_of: date
    holdings: list[FundHolding]
    total_market_value: Decimal
    pending_amount: Decimal
    official_nav_count: int
    estimated_nav_count: int
    missing_nav_count: int


@dependency
def cal_market_value(
    *,
    as_of: date | None = None,
    use_estimate: bool = False,
    trade_repo: TradeRepo | None = None,
    fund_repo: FundRepo | None = None,
    nav_repo: NavRepo | None = None,
    eastmoney_service: EastmoneyClient | None = None,
    calendar_service: CalendarService | None = None,
) -> MarketValueResult:
    """
    计算指定日期的持仓市值（v0.4.2+）。

    功能：
        - 计算指定日期的持仓市值；
        - 优先使用当日官方净值；
        - 净值缺失时的回退策略由 use_estimate 控制。

    Args:
        as_of: 查询日期，None 时默认使用上一交易日。
        use_estimate: 净值缺失时的回退策略（默认 False）。
            - False: 向前查找最近 7 个交易日的官方净值；
            - True: 使用盘中估值（仅限最近 3 天）。
        trade_repo: 交易仓储（自动注入）。
        fund_repo: 基金仓储（自动注入）。
        nav_repo: 净值仓储（自动注入）。
        eastmoney_service: 东方财富客户端（自动注入）。
        calendar_service: 日历服务（自动注入）。

    Returns:
        MarketValueResult：持仓市值及明细。
    """
    # 0. 默认日期：上一交易日
    if as_of is None:
        today = date.today()
        as_of = calendar_service.prev_open("CN_A", today)
        if as_of is None:
            # 日历数据缺失时降级为昨天
            from datetime import timedelta

            as_of = today - timedelta(days=1)

    # 1. 查询持仓和待确认金额
    holdings_data = trade_repo.get_position(up_to=as_of)
    pending_amt = trade_repo.get_pending_amount(up_to=as_of)

    if not holdings_data:
        return MarketValueResult(
            as_of=as_of,
            holdings=[],
            total_market_value=Decimal("0"),
            pending_amount=pending_amt,
            official_nav_count=0,
            estimated_nav_count=0,
            missing_nav_count=0,
        )

    # 2. 构建持仓对象
    holdings: list[FundHolding] = []
    for fund_code, shares in holdings_data.items():
        fund = fund_repo.get(fund_code)
        holdings.append(
            FundHolding(
                fund_code=fund_code,
                fund_name=fund.name if fund else fund_code,
                shares=shares,
            )
        )

    # 3. 获取净值
    official_count = 0
    estimated_count = 0
    missing_count = 0

    for holding in holdings:
        # 3.1 尝试当天官方净值
        nav = nav_repo.get(holding.fund_code, as_of)
        if nav is not None and nav > 0:
            holding.nav = nav
            holding.nav_source = "官方"
            holding.market_value = holding.shares * nav
            official_count += 1
            continue

        # 3.2 回退策略
        if use_estimate:
            # 估值模式（仅限最近 3 天）
            days_diff = (date.today() - as_of).days
            if days_diff <= 3:
                est_result = eastmoney_service.get_nav_estimate(holding.fund_code)
                if est_result:
                    holding.nav, holding.estimated_time = est_result
                    holding.nav_source = "估值"
                    holding.market_value = holding.shares * holding.nav
                    estimated_count += 1
                    continue
        else:
            # 净值模式：向前查找最近 7 个交易日
            check_day = as_of
            for _ in range(7):
                prev_day = calendar_service.prev_open("CN_A", check_day)
                if not prev_day:
                    break
                prev_nav = nav_repo.get(holding.fund_code, prev_day)
                if prev_nav is not None and prev_nav > 0:
                    holding.nav = prev_nav
                    holding.nav_source = f"官方({prev_day})"
                    holding.market_value = holding.shares * prev_nav
                    official_count += 1
                    break
                check_day = prev_day
            if holding.market_value is not None:
                continue

        # 3.3 无法获取净值
        holding.nav_source = "缺失"
        missing_count += 1

    # 4. 计算总市值
    total_mv = sum(
        (h.market_value for h in holdings if h.market_value is not None),
        start=Decimal("0"),
    )

    return MarketValueResult(
        as_of=as_of,
        holdings=holdings,
        total_market_value=total_mv,
        pending_amount=pending_amt,
        official_nav_count=official_count,
        estimated_nav_count=estimated_count,
        missing_nav_count=missing_count,
    )
