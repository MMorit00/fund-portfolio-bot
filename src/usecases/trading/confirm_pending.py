from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.core.protocols import NavProtocol, TradeRepo
from src.core.trading.precision import quantize_shares


@dataclass(slots=True)
class ConfirmResult:
    """确认结果统计（v0.2.1：新增延迟追踪）。"""

    confirmed_count: int
    skipped_count: int
    skipped_funds: list[str]
    delayed_count: int  # v0.2.1: 标记为延迟的交易数


class ConfirmPendingTrades:
    """
    将到达确认日的 pending 交易按官方净值确认份额。

    口径（v0.2.1）：
    - 仅使用"定价日 NAV"（pricing_date = next_trading_day_or_self(trade_date)），
      份额 = 金额 / 定价日 NAV；
    - 若定价日 NAV 缺失或 <= 0：
      * 若 today >= confirm_date，标记为 delayed（延迟）；
      * 否则跳过，留待后续重试；
    - 确认日来源于 DB 预写的 confirm_date（写入时按当时规则计算），此处不再重算。
    """

    def __init__(self, trade_repo: TradeRepo, nav_provider: NavProtocol) -> None:
        self.trade_repo = trade_repo
        self.nav_provider = nav_provider

    def execute(self, *, today: date) -> ConfirmResult:
        """
        执行当日的交易确认。

        逻辑（v0.2.1）：
        1. today < confirm_date → 正常等待
        2. today >= confirm_date 且 NAV 存在 → 正常确认，confirmation_status=normal
        3. today >= confirm_date 且 NAV 缺失 → 标记 delayed，不修改 confirm_date

        Args:
            today: 运行日；从仓储中读取 `confirm_date=today` 的 pending 交易。

        Returns:
            确认结果统计（confirmed_count / delayed_count / skipped_count）。

        副作用：
            - 将符合条件的交易状态更新为 `confirmed`，写入份额与确认用 NAV（定价日 NAV）。
            - 将超期但 NAV 缺失的交易标记为 DELAYED。
        """

        # 找到今天应确认的交易（按交易日+T+N）
        to_confirm = self.trade_repo.list_pending_to_confirm(today)

        confirmed_count = 0
        skipped_count = 0
        delayed_count = 0
        skipped_funds_set: set[str] = set()

        for t in to_confirm:
            # 仅使用定价日 NAV（由 TradeRepo.add 写入时计算，保证非空）
            pricing_day = t.pricing_date
            if pricing_day is None:
                raise ValueError(f"交易记录缺少 pricing_date：trade_id={t.id}")
            nav = self.nav_provider.get_nav(t.fund_code, pricing_day)

            if nav is not None and nav > Decimal("0"):
                # 正常确认（confirm 方法已包含重置延迟标记）
                shares = quantize_shares(t.amount / nav)
                self.trade_repo.confirm(t.id or 0, shares, nav)
                confirmed_count += 1
            else:
                # NAV 缺失
                if t.confirm_date and today >= t.confirm_date:
                    # 已到/超过理论确认日 → 标记延迟
                    t.confirmation_status = "delayed"
                    t.delayed_reason = "nav_missing"
                    if t.delayed_since is None:
                        t.delayed_since = today
                    self.trade_repo.update(t)
                    delayed_count += 1
                else:
                    # 未到确认日，正常跳过
                    skipped_count += 1
                    skipped_funds_set.add(t.fund_code)

        return ConfirmResult(
            confirmed_count=confirmed_count,
            skipped_count=skipped_count,
            skipped_funds=sorted(skipped_funds_set),
            delayed_count=delayed_count,
        )
