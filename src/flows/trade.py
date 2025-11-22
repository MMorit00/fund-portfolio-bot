from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.core.dependency import dependency
from src.core.models.trade import Trade
from src.core.rules.precision import quantize_shares
from src.data.client.local_nav import LocalNavService
from src.data.db.fund_repo import FundRepo
from src.data.db.trade_repo import TradeRepo


@dependency
def create_trade(
    *,
    fund_code: str,
    trade_type: str,
    amount: Decimal,
    trade_day: date,
    trade_repo: TradeRepo | None = None,
    fund_repo: FundRepo | None = None,
) -> Trade:
    """
    创建一笔买入/卖出交易（pending）。

    Args:
        fund_code: 基金代码，需已存在于 funds 表。
        trade_type: 交易类型，`buy` 或 `sell`。
        amount: 金额，必须大于 0（Decimal）。
        trade_day: 交易日期（下单/约定日）。
        trade_repo: 交易仓储（可选，自动注入）。
        fund_repo: 基金仓储（可选，自动注入）。

    Returns:
        入库后的 Trade 实体（包含生成的 id）。

    Raises:
        ValueError: 基金不存在或 market 配置无效。

    说明：
        - 金额使用 Decimal
        - 市场类型从 FundRepo 读取
        - 通过 @inject_deps 装饰器自动注入依赖
        - 测试时可传入 Mock 对象覆盖默认依赖
    """
    # trade_repo 和 fund_repo 已通过装饰器自动注入，直接使用
    fund = fund_repo.get_fund(fund_code)
    if not fund:
        raise ValueError(f"未知基金代码：{fund_code}")

    trade = Trade(
        id=None,
        fund_code=fund_code,
        type=trade_type,
        amount=amount,
        trade_date=trade_day,
        status="pending",
        market=fund.market,
    )
    return trade_repo.add(trade)


@dataclass(slots=True)
class ConfirmResult:
    """确认结果统计（v0.2.1：新增延迟追踪）。"""

    confirmed_count: int
    skipped_count: int
    skipped_funds: list[str]
    delayed_count: int


@dependency
def confirm_trades(
    *,
    today: date,
    trade_repo: TradeRepo | None = None,
    nav_service: LocalNavService | None = None,
) -> ConfirmResult:
    """
    将到达确认日的 pending 交易按官方净值确认份额。

    口径（v0.2.1）：
    - 仅使用"定价日 NAV"（pricing_date = next_trading_day_or_self(trade_date)），
      份额 = 金额 / 定价日 NAV；
    - 若定价日 NAV 缺失或 <= 0：
      * 若 today >= confirm_date，标记为 delayed（延迟）；
      * 否则跳过，留待后续重试；
    - 确认日来源于 DB 预写的 confirm_date（写入时按当时规则计算），此处不再重算。

    逻辑（v0.2.1）：
    1. today < confirm_date → 正常等待
    2. today >= confirm_date 且 NAV 存在 → 正常确认，confirmation_status=normal
    3. today >= confirm_date 且 NAV 缺失 → 标记 delayed，不修改 confirm_date

    Args:
        today: 运行日；从仓储中读取 `confirm_date=today` 的 pending 交易。
        trade_repo: 交易仓储（可选，自动注入）。
        nav_service: 净值查询服务（可选，自动注入）。

    Returns:
        确认结果统计（confirmed_count / delayed_count / skipped_count）。

    副作用：
        - 将符合条件的交易状态更新为 `confirmed`，写入份额与确认用 NAV（定价日 NAV）。
        - 将超期但 NAV 缺失的交易标记为 DELAYED。
    """
    # trade_repo 和 nav_service 已通过装饰器自动注入
    # 找到今天应确认的交易（按交易日+T+N）
    to_confirm = trade_repo.list_pending_to_confirm(today)

    confirmed_count = 0
    skipped_count = 0
    delayed_count = 0
    skipped_funds_set: set[str] = set()

    for t in to_confirm:
        # 仅使用定价日 NAV（由 TradeRepo.add 写入时计算，保证非空）
        pricing_day = t.pricing_date
        if pricing_day is None:
            raise ValueError(f"交易记录缺少 pricing_date：trade_id={t.id}")
        nav = nav_service.get_nav(t.fund_code, pricing_day)

        if nav is not None and nav > Decimal("0"):
            # 正常确认（confirm 方法已包含重置延迟标记）
            shares = quantize_shares(t.amount / nav)
            trade_repo.confirm(t.id or 0, shares, nav)
            confirmed_count += 1
        else:
            # NAV 缺失
            if t.confirm_date and today >= t.confirm_date:
                # 已到/超过理论确认日 → 标记延迟
                t.confirmation_status = "delayed"
                t.delayed_reason = "nav_missing"
                if t.delayed_since is None:
                    t.delayed_since = today
                trade_repo.update(t)
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
