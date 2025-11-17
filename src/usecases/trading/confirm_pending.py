from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.core.trading.calendar import TradingCalendar
from src.core.trading.precision import quantize_shares
from src.usecases.ports import NavProvider, TradeRepo


@dataclass(slots=True)
class ConfirmResult:
    """确认结果统计。"""

    confirmed_count: int
    skipped_count: int
    skipped_funds: list[str]


class ConfirmPendingTrades:
    """
    将到达确认日的 pending 交易按官方净值确认份额。

    口径（v0.2）：
    - 仅使用“定价日 NAV”（pricing_date = next_trading_day_or_self(trade_date)），
      份额 = 金额 / 定价日 NAV；
    - 若定价日 NAV 缺失或 <= 0，则跳过，留待后续重试；
    - 确认日来源于 DB 预写的 confirm_date（写入时按当时规则计算），此处不再重算。
    """

    def __init__(self, trade_repo: TradeRepo, nav_provider: NavProvider, calendar: TradingCalendar) -> None:
        self.trade_repo = trade_repo
        self.nav_provider = nav_provider
        self.calendar = calendar

    def execute(self, *, today: date) -> ConfirmResult:
        """
        执行当日的交易确认。

        Args:
            today: 运行日；从仓储中读取 `confirm_date=today` 的 pending 交易。

        Returns:
            成功确认的交易数量。

        副作用：
            - 将符合条件的交易状态更新为 `confirmed`，写入份额与确认用 NAV（定价日 NAV）。
        """

        # 找到今天应确认的交易（按交易日+T+N）
        # 简化：由仓储直接提供 today 应确认的 pending（实现可基于 get_confirm_date 过滤）
        to_confirm = self.trade_repo.list_pending_to_confirm(today)

        confirmed_count = 0
        skipped_count = 0
        skipped_funds_set: set[str] = set()
        for t in to_confirm:
            # 仅使用定价日 NAV（定价日=交易日或其后首个交易日）；缺失/无效则跳过
            pricing_day = self.calendar.next_trading_day_or_self(t.trade_date, market=t.market)
            nav = self.nav_provider.get_nav(t.fund_code, pricing_day)
            if nav is None or nav <= Decimal("0"):
                # 无净值数据，留待后续重试
                skipped_count += 1
                skipped_funds_set.add(t.fund_code)
                continue

            shares = quantize_shares(t.amount / nav)
            self.trade_repo.confirm(t.id or 0, shares, nav)
            confirmed_count += 1
        return ConfirmResult(
            confirmed_count=confirmed_count,
            skipped_count=skipped_count,
            skipped_funds=sorted(skipped_funds_set),
        )
