"""Quick-and-dirty script to seed SQLite with sample data for local testing."""

from __future__ import annotations

from datetime import date
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


def main() -> None:
    helper = SqliteDbHelper()
    helper.init_schema_if_needed()
    conn = helper.get_connection()

    fund_repo = SqliteFundRepo(conn)
    trade_repo = SqliteTradeRepo(conn)
    nav_repo = SqliteNavRepo(conn)
    dca_repo = SqliteDcaPlanRepo(conn)
    alloc_repo = SqliteAllocConfigRepo(conn)

    # Seed funds
    fund_repo.add_fund("110022", "Test Equity", AssetClass.CSI300, "A")
    fund_repo.add_fund("000001", "Test QDII", AssetClass.US_QDII, "QDII")

    # Seed DCA plan (overwrites if exists)
    with conn:
        conn.execute("DELETE FROM dca_plans")
        conn.execute(
            "INSERT INTO dca_plans(fund_code, amount, frequency, rule) VALUES(?, ?, ?, ?)",
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

    # Seed navs
    today = date.today()
    nav_repo.upsert("110022", today, Decimal("1.2345"))
    nav_repo.upsert("000001", today, Decimal("0.8765"))

    # Create a sample trade
    trade = Trade(
        id=None,
        fund_code="110022",
        type="buy",
        amount=Decimal("1000"),
        trade_date=today,
        status="pending",
        market="A",
    )
    saved = trade_repo.add(trade)
    print(f"Inserted trade id={saved.id}, confirm_date preset")

    # Print pending list for confirm_date
    confirm_day = get_confirm_date(trade.market, trade.trade_date)
    pending = trade_repo.list_pending_to_confirm(confirm_day)
    print(f"Pending with confirm_date={confirm_day.isoformat()}: {len(pending)}")

    positions = trade_repo.position_shares()
    print("Current confirmed positions:", positions)

    print("Target weights:", alloc_repo.get_target_weights())


if __name__ == "__main__":
    main()
