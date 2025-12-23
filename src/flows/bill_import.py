"""账单导入逻辑。

职责：
- import_bill(): 将账单记录导入数据库（trades + action_log）

流程：CSV → 解析 → BillFacts 分析 → 用户确认 → 写库
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.dependency import dependency
from src.core.log import log
from src.core.models.action import ActionLog
from src.core.models.bill import BillItem
from src.core.models.trade import MarketType, Trade
from src.data.db.action_repo import ActionRepo
from src.data.db.fund_repo import FundRepo
from src.data.db.import_batch_repo import ImportBatchRepo
from src.data.db.trade_repo import TradeRepo

# 交易类型 → ActionLog.strategy 映射
STRATEGY_MAP: dict[str, str | None] = {
    "dca_buy": "dca",
    "normal_buy": None,
}


@dataclass(slots=True)
class ImportError:
    """导入错误记录。"""

    order_id: str
    fund_code: str
    error: str


@dataclass(slots=True)
class ImportResult:
    """导入结果。"""

    batch_id: int
    total: int  # 总记录数
    imported: int  # 成功导入
    skipped: int  # 跳过（重复）
    failed: int  # 失败（基金不存在等）
    errors: list[ImportError] = field(default_factory=list)


@dependency
def import_bill(
    items: list[BillItem],
    source: str = "alipay_pdf",
    note: str | None = None,
    *,
    fund_repo: FundRepo | None = None,
    trade_repo: TradeRepo | None = None,
    action_repo: ActionRepo | None = None,
    import_batch_repo: ImportBatchRepo | None = None,
) -> ImportResult:
    """导入账单记录到数据库。

    Args:
        items: 解析后的账单记录列表
        source: 来源标识
        note: 可选备注

    Returns:
        导入结果
    """
    if not items:
        log("[BillImport] 没有需要导入的记录")
        return ImportResult(batch_id=0, total=0, imported=0, skipped=0, failed=0)

    # 创建导入批次
    batch_id = import_batch_repo.create(source=source, note=note)
    log(f"[BillImport] 创建导入批次 batch_id={batch_id}")

    imported = 0
    skipped = 0
    failed = 0
    errors: list[ImportError] = []

    for item in items:
        # 检查重复（按订单号）
        if trade_repo.exists_by_external_id(item.order_id):
            log(f"[BillImport] 跳过重复记录: {item.order_id}")
            skipped += 1
            continue

        # 查找基金
        fund = fund_repo.get(item.fund_code)
        if not fund:
            log(f"[BillImport] 基金不存在: {item.fund_code}")
            errors.append(
                ImportError(
                    order_id=item.order_id,
                    fund_code=item.fund_code,
                    error=f"基金不存在: {item.fund_code}",
                )
            )
            failed += 1
            continue

        # 创建交易记录
        try:
            trade = _create_trade(item, fund.market, batch_id, trade_repo)
            _create_action_log(item, trade.id, action_repo)
            imported += 1
            log(f"[BillImport] 导入成功: {item.fund_code} {item.confirm_amount}")
        except Exception as e:  # noqa: BLE001
            log(f"[BillImport] 导入失败: {item.order_id} - {e}")
            errors.append(
                ImportError(
                    order_id=item.order_id,
                    fund_code=item.fund_code,
                    error=str(e),
                )
            )
            failed += 1

    log(
        f"[BillImport] 完成: 总计={len(items)}, 导入={imported}, "
        f"跳过={skipped}, 失败={failed}"
    )

    return ImportResult(
        batch_id=batch_id,
        total=len(items),
        imported=imported,
        skipped=skipped,
        failed=failed,
        errors=errors,
    )


def _create_trade(
    item: BillItem,
    market: MarketType,
    batch_id: int,
    trade_repo: TradeRepo,
) -> Trade:
    """创建交易记录。"""
    # 确认金额作为 amount（已确认的实际金额）
    # 申请金额存入 apply_amount
    trade = Trade(
        id=None,
        fund_code=item.fund_code,
        type="buy",  # 当前 CSV 只有买入记录
        amount=item.confirm_amount,
        trade_date=item.trade_time.date(),
        status="confirmed",  # CSV 中的记录都是已确认的
        market=market,
        shares=item.confirm_shares,
        remark=f"账单导入: {item.fund_name}",
        external_id=item.order_id,
        import_batch_id=batch_id,
        fee=item.fee,
        apply_amount=item.apply_amount,
    )
    return trade_repo.add(trade)


def _create_action_log(
    item: BillItem,
    trade_id: int | None,
    action_repo: ActionRepo,
) -> ActionLog:
    """创建行为日志。"""
    strategy = STRATEGY_MAP.get(item.trade_type)

    action_log = ActionLog(
        id=None,
        action="buy",
        actor="human",
        source="import",
        acted_at=item.trade_time,
        fund_code=item.fund_code,
        target_date=item.confirm_date,
        trade_id=trade_id,
        strategy=strategy,
        note=f"账单导入: {item.trade_type}",
    )
    return action_repo.add(action_log)


@dependency
def check_funds_exist(
    items: list[BillItem],
    *,
    fund_repo: FundRepo | None = None,
) -> tuple[list[str], list[str]]:
    """检查账单中的基金是否都存在于数据库。

    Args:
        items: 账单记录列表

    Returns:
        (existing_codes, missing_codes): 存在的基金代码列表和缺失的基金代码列表
    """
    codes = {item.fund_code for item in items}

    existing: list[str] = []
    missing: list[str] = []

    for code in sorted(codes):
        if fund_repo.get(code):
            existing.append(code)
        else:
            missing.append(code)

    return existing, missing
