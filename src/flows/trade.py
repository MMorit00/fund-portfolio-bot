from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from src.core.dependency import dependency
from src.core.models import ActionLog, Intent, Trade
from src.core.rules.precision import quantize_shares
from src.data.client.local_nav import LocalNavService
from src.data.db.action_repo import ActionRepo
from src.data.db.fund_repo import FundRepo
from src.data.db.trade_repo import TradeRepo


@dependency
def create_trade(
    *,
    fund_code: str,
    trade_type: str,
    amount: Decimal,
    trade_day: date,
    intent: Intent | None = None,
    note: str | None = None,
    _log_action: bool = True,
    trade_repo: TradeRepo | None = None,
    fund_repo: FundRepo | None = None,
    action_repo: ActionRepo | None = None,
) -> Trade:
    """
    创建一笔买入/卖出交易（pending）。

    Args:
        fund_code: 基金代码，需已存在于 funds 表。
        trade_type: 交易类型，`buy` 或 `sell`。
        amount: 金额，必须大于 0（Decimal）。
        trade_day: 交易日期（下单/约定日）。
        intent: 意图标签（planned/impulse/opportunistic/exit/rebalance）。
        note: 人话备注。
        _log_action: 是否记录行为日志（DCA 等自动场景应传 False）。
        trade_repo: 交易仓储（可选，自动注入）。
        fund_repo: 基金仓储（可选，自动注入）。
        action_repo: 行为日志仓储（可选，自动注入）。

    Returns:
        入库后的 Trade 实体（包含生成的 id）。

    Raises:
        ValueError: 基金不存在或 market 配置无效。

    说明：
        - 金额使用 Decimal
        - 市场类型从 FundRepo 读取
        - 通过 @dependency 装饰器自动注入依赖
        - 测试时可传入 Mock 对象覆盖默认依赖
    """
    # 1. 验证基金存在
    fund = fund_repo.get(fund_code)
    if not fund:
        raise ValueError(f"未知基金代码：{fund_code}")

    # 2. 创建并保存交易记录
    trade = Trade(
        id=None,
        fund_code=fund_code,
        type=trade_type,
        amount=amount,
        trade_date=trade_day,
        status="pending",
        market=fund.market,
    )
    saved_trade = trade_repo.add(trade)

    # 3. 记录行为日志（仅手动交易，DCA 等自动场景不记录）
    if _log_action and action_repo is not None:
        action_repo.add(
            ActionLog(
                id=None,
                action=trade_type,  # buy / sell
                actor="human",
                source="manual",
                acted_at=datetime.now(),
                fund_code=fund_code,
                target_date=trade_day,
                trade_id=saved_trade.id,
                intent=intent,
                strategy="none",
                note=note,
            )
        )

    # 4. 返回已保存的交易
    return saved_trade


@dataclass(slots=True)
class ConfirmResult:
    """
    确认结果统计（v0.2.1：新增延迟追踪）。
    
    包含多维度统计：
    - confirmed_count: 成功确认数量
    - skipped_count: 跳过数量（未到确认日）
    - delayed_count: 延迟数量（NAV 缺失）
    - skipped_funds: 跳过的基金代码列表
    
    用于 CLI 展示确认进度和异常情况。
    """

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
    # 1. 获取待确认交易
    to_confirm = trade_repo.list_pending(today)

    # 2. 初始化统计计数器
    confirmed_count = 0
    skipped_count = 0
    delayed_count = 0
    skipped_funds_set: set[str] = set()

    # 3. 遍历交易并确认
    for t in to_confirm:
        # 3.1 验证定价日
        pricing_day = t.pricing_date
        if pricing_day is None:
            raise ValueError(f"交易记录缺少 pricing_date：trade_id={t.id}")

        # 3.2 获取定价日 NAV
        nav = nav_service.get_nav(t.fund_code, pricing_day)

        # 3.3 根据 NAV 可用性处理
        if nav is not None and nav > Decimal("0"):
            # NAV 可用 → 正常确认
            shares = quantize_shares(t.amount / nav)
            trade_repo.confirm(t.id or 0, shares)
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

    # 4. 返回统计结果
    return ConfirmResult(
        confirmed_count=confirmed_count,
        skipped_count=skipped_count,
        skipped_funds=sorted(skipped_funds_set),
        delayed_count=delayed_count,
    )


@dependency
def list_trades(
    *,
    status: str | None = None,
    trade_repo: TradeRepo | None = None,
) -> list[Trade]:
    """
    查询交易记录（v0.3.2）。

    Args:
        status: 交易状态（pending/confirmed/skipped），None 表示查询所有状态。
        trade_repo: 交易仓储（可选，自动注入）。

    Returns:
        交易列表，按 trade_date 降序、id 降序排列。
    """
    # 1. 按状态查询
    if status is not None:
        return trade_repo.list_by_status(status)

    # 2. status=None 时，合并所有状态的交易
    all_trades: list[Trade] = []
    for s in ["pending", "confirmed", "skipped"]:
        all_trades.extend(trade_repo.list_by_status(s))

    # 3. 排序并返回
    all_trades.sort(key=lambda t: (t.trade_date, t.id or 0), reverse=True)
    return all_trades


@dependency
def cancel_trade(
    *,
    trade_id: int,
    note: str | None = None,
    trade_repo: TradeRepo | None = None,
    action_repo: ActionRepo | None = None,
) -> None:
    """
    取消 pending 交易（v0.3.4 新增，v0.4.1 添加埋点）。

    Args:
        trade_id: 交易 ID。
        note: 取消原因备注（可选）。
        trade_repo: 交易仓储（可选，自动注入）。
        action_repo: 行为日志仓储（可选，自动注入）。

    Raises:
        ValueError: 交易不存在或不是 pending 状态时抛出。

    副作用：
        将指定交易的 status 从 pending 更新为 skipped。
    """
    # 1. 取消交易
    trade_repo.cancel(trade_id)

    # 2. 记录行为日志
    if action_repo is not None:
        action_repo.add(
            ActionLog(
                id=None,
                action="cancel",
                actor="human",
                source="manual",
                acted_at=datetime.now(),
                fund_code=None,
                target_date=None,
                trade_id=trade_id,
                intent=None,
                strategy="none",
                note=note,
            )
        )


@dependency
def confirm_trade_manual(
    *,
    trade_id: int,
    shares: Decimal,
    nav: Decimal,
    trade_repo: TradeRepo | None = None,
) -> None:
    """
    手动确认 pending 交易（v0.3.4+ 新增，应对 NAV 永久缺失场景）。

    使用场景：
    - 支付宝等平台订单已成功，但系统 NAV 持续缺失（基金停牌、数据源故障）
    - 用户从平台复制 NAV 和份额，手动确认系统交易记录

    Args:
        trade_id: 交易 ID（必须是 pending 状态）。
        shares: 确认份额（从支付宝等平台复制，Decimal 类型）。
        nav: 确认净值（从支付宝等平台复制，Decimal 类型）。
        trade_repo: 交易仓储（可选，自动注入）。

    Raises:
        ValueError: 交易不存在、不是 pending 状态、或参数无效时抛出。

    副作用：
        将交易状态更新为 confirmed，写入份额与净值，重置延迟标记。

    注意：
        - NAV 和 shares 必须大于 0
        - 建议仅在 NAV 延迟超过 3 天后使用
        - 确认后无法撤销，请仔细核对数据
    """
    # 1. 验证参数
    if shares <= Decimal("0"):
        raise ValueError(f"份额必须大于 0：{shares}")
    if nav <= Decimal("0"):
        raise ValueError(f"净值必须大于 0：{nav}")

    shares = quantize_shares(shares)

    # 2. 验证交易状态
    trade = trade_repo.get(trade_id)
    if not trade:
        raise ValueError(f"交易不存在：trade_id={trade_id}")
    if trade.status != "pending":
        raise ValueError(f"只能确认 pending 交易：trade_id={trade_id}，当前状态={trade.status}")

    # 3. 确认交易（会自动重置延迟标记）
    trade_repo.confirm(trade_id, shares)
