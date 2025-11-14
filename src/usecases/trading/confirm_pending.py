from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.core.trading.settlement import get_confirm_date
from src.usecases.ports import NavProvider, TradeRepo


class ConfirmPendingTrades:
    """
    将到达确认日的 pending 交易按官方净值确认份额。

    MVP 简化：
    - 若确认日无净值，跳过（入口层可重试）；
    - 份额 = 金额 / 当日净值；
    - 份额/净值均使用 Decimal。
    """

    def __init__(self, trade_repo: TradeRepo, nav_provider: NavProvider) -> None:
        self.trade_repo = trade_repo
        self.nav_provider = nav_provider

    def execute(self, *, today: date) -> int:
        """返回本次确认成功的交易数量。"""

        # 找到今天应确认的交易（按交易日+T+N）
        # 简化：由仓储直接提供 today 应确认的 pending（实现可基于 get_confirm_date 过滤）
        to_confirm = self.trade_repo.list_pending_to_confirm(today)

        confirmed_count = 0
        for t in to_confirm:
            confirm_day = get_confirm_date(t.market, t.trade_date)
            if confirm_day != today:
                continue

            nav = self.nav_provider.get_nav(t.fund_code, today)
            if nav is None or nav <= Decimal("0"):
                # 无净值数据，留待后续重试
                continue

            shares = (t.amount / nav)
            self.trade_repo.confirm(t.id or 0, shares, nav)
            confirmed_count += 1
        return confirmed_count

