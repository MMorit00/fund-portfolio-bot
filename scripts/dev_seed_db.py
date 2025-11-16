"""Quick-and-dirty script to seed SQLite with sample data for local testing.

改进要点（一致性）：
- NAV 的日期与交易定价口径对齐：首选“交易日 NAV”。
- 为 status/日报市值视图提供“当日 NAV”。
- 提供可复现的演示：将 A 股样例设置为“前一工作日交易”，当日即可确认（T+1）。
- 可选择重置表数据，避免历史数据干扰。
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal

from src.adapters.db.sqlite.alloc_config_repo import SqliteAllocConfigRepo
from src.adapters.db.sqlite.db_helper import SqliteDbHelper
from src.adapters.db.sqlite.dca_plan_repo import SqliteDcaPlanRepo
from src.adapters.db.sqlite.fund_repo import SqliteFundRepo
from src.adapters.db.sqlite.nav_repo import SqliteNavRepo
from src.adapters.db.sqlite.trade_repo import SqliteTradeRepo
from src.core.asset_class import AssetClass
from src.core.dca_plan import DcaPlan
from src.core.trade import Trade
from src.core.trading.settlement import get_confirm_date
from src.usecases.trading.confirm_pending import ConfirmPendingTrades
from src.app.wiring import LocalNavProvider
from src.core.trading.calendar import SimpleTradingCalendar


def prev_business_day(d: date, n: int = 1) -> date:
    """
    返回 d 之前的第 n 个工作日（仅考虑周末）。

    Args:
        d: 参考日期。
        n: 向前追溯的工作日数量，默认 1。

    Returns:
        目标工作日日期。
    """
    days = 0
    cur = d
    while days < n:
        cur = cur - timedelta(days=1)
        if cur.weekday() < 5:
            days += 1
    return cur


def main() -> None:
    """
    初始化开发用 SQLite 数据：基金/定投/配置/净值/样例交易。

    行为：可通过 `SEED_RESET`/`SEED_SIMULATE_CONFIRM` 控制重置与自动确认。
    """
    helper = SqliteDbHelper()
    helper.init_schema_if_needed()
    conn = helper.get_connection()

    fund_repo = SqliteFundRepo(conn)
    calendar = SimpleTradingCalendar()
    trade_repo = SqliteTradeRepo(conn, calendar)
    nav_repo = SqliteNavRepo(conn)
    dca_repo = SqliteDcaPlanRepo(conn)
    alloc_repo = SqliteAllocConfigRepo(conn)

    # 可选：重置核心表，避免历史数据干扰
    reset = os.getenv("SEED_RESET", "1") == "1"
    if reset:
        with conn:
            conn.execute("DELETE FROM trades")
            conn.execute("DELETE FROM navs")
            conn.execute("DELETE FROM funds")
            conn.execute("DELETE FROM dca_plans")
            conn.execute("DELETE FROM alloc_config")

    # Seed funds（幂等）
    fund_repo.add_fund("110022", "Test Equity", AssetClass.CSI300, "A")
    fund_repo.add_fund("000001", "Test QDII", AssetClass.US_QDII, "QDII")

    # Seed DCA plan
    with conn:
        conn.execute(
            "INSERT INTO dca_plans(fund_code, amount, frequency, rule) VALUES(?, ?, ?, ?)"
            " ON CONFLICT(fund_code) DO UPDATE SET amount=excluded.amount, frequency=excluded.frequency, rule=excluded.rule",
            ("110022", "1000", "weekly", "MON"),
        )

    # Seed alloc config
    with conn:
        conn.execute("DELETE FROM alloc_config")
        conn.executemany(
            "INSERT INTO alloc_config(asset_class, target_weight, max_deviation) VALUES(?, ?, ?)",
            [
                (AssetClass.CSI300.value, "0.5", "0.05"),
                (AssetClass.US_QDII.value, "0.3", "0.05"),
                (AssetClass.CGB_3_5Y.value, "0.2", "0.03"),
            ],
        )

    # 日期选择：A 股示例用“前一工作日”为交易日，使 confirm_date = 今天（T+1）
    today = date.today()
    trade_day_a = prev_business_day(today, 1)

    # Seed NAV：
    # - 交易日 NAV（用于确认份额，符合口径）
    # - 当日 NAV（用于市值视图 status/日报）
    nav_repo.upsert("110022", trade_day_a, Decimal("1.2000"))
    nav_repo.upsert("110022", today, Decimal("1.2345"))
    nav_repo.upsert("000001", today, Decimal("0.8765"))

    # Create a sample trade（A 股，交易日=前一工作日，今天应确认）
    trade = Trade(
        id=None,
        fund_code="110022",
        type="buy",
        amount=Decimal("1000"),
        trade_date=trade_day_a,
        status="pending",
        market="A",
    )
    saved = trade_repo.add(trade)
    print(f"Inserted trade id={saved.id}, trade_date={trade_day_a}, confirm_date preset")

    # Print pending list for confirm_date
    confirm_day = get_confirm_date(trade.market, trade_day_a, calendar)
    pending = trade_repo.list_pending_to_confirm(confirm_day)
    print(f"Pending with confirm_date={confirm_day.isoformat()}: {len(pending)}")

    # 自动执行一次确认，便于演示：默认模拟"在确认日"运行（对任意实际日期可复现）
    # 开关：SEED_SIMULATE_CONFIRM（优先）或兼容 SEED_CONFIRM（均默认开启）
    if os.getenv("SEED_SIMULATE_CONFIRM", os.getenv("SEED_CONFIRM", "1")) == "1":
        confirmed = ConfirmPendingTrades(trade_repo, LocalNavProvider(nav_repo), calendar).execute(today=confirm_day)
        print(f"Confirmed on confirm_day({confirm_day}): {confirmed}")

    positions = trade_repo.position_shares()
    print("Current confirmed positions:", positions)

    print("Target weights:", alloc_repo.get_target_weights())


if __name__ == "__main__":
    main()
