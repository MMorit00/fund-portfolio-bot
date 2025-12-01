"""开发环境数据初始化脚本（v0.3.2 版本）。

职责：
- 初始化开发用 SQLite 数据：基金/定投/配置/净值/样例交易
- 填充基础交易日历数据（CN_A 最近 30 天）
- 创建可复现的测试场景

使用方式：
    SEED_RESET=1 python -m scripts.dev_seed_db           # 重置所有数据
    SEED_CREATE_DELAYED_TRADE=1 python -m scripts.dev_seed_db  # 创建延迟交易测试场景

环境变量：
    SEED_RESET: 是否重置核心表数据（默认 1）
    SEED_SIMULATE_CONFIRM: 是否自动运行一次确认（默认 1）
    SEED_CREATE_DELAYED_TRADE: 是否创建延迟交易测试场景（默认 0）
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal

from src.core.models.asset_class import AssetClass
from src.core.models.trade import Trade
from src.core.rules.settlement import calc_settlement_dates, default_policy
from src.data.db.alloc_config_repo import AllocConfigRepo
from src.data.db.calendar import CalendarService
from src.data.db.db_helper import DbHelper
from src.data.db.dca_plan_repo import DcaPlanRepo
from src.data.db.fund_repo import FundRepo
from src.data.db.nav_repo import NavRepo
from src.data.db.trade_repo import TradeRepo
from src.flows.trade import confirm_trades


def _seed_basic_calendar(conn, today: date, days_back: int = 30) -> None:
    """
    填充基础交易日历数据（简化版：工作日 = 交易日）。

    仅用于开发测试，生产环境应使用 sync_calendar/patch_calendar。

    Args:
        conn: 数据库连接
        today: 当前日期
        days_back: 向前填充的天数（默认 30 天）
    """
    # 确保表存在
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trading_calendar (
            market TEXT NOT NULL,
            day TEXT NOT NULL,
            is_trading_day INTEGER NOT NULL CHECK(is_trading_day IN (0,1)),
            PRIMARY KEY (market, day)
        )
    """)

    rows = []
    for i in range(days_back + 10):  # 多填充 10 天以覆盖 T+N
        d = today - timedelta(days=days_back - i)
        is_trading = 1 if d.weekday() < 5 else 0
        rows.append(("CN_A", d.isoformat(), is_trading))

    with conn:
        conn.executemany(
            """
            INSERT INTO trading_calendar(market, day, is_trading_day)
            VALUES (?, ?, ?)
            ON CONFLICT(market, day) DO UPDATE SET is_trading_day=excluded.is_trading_day
            """,
            rows,
        )
    print(f"[DevSeed] 已填充 {len(rows)} 天的 CN_A 交易日历（工作日=交易日）")


def _prev_business_day(d: date, calendar: CalendarService, n: int = 1) -> date:
    """
    返回 d 之前的第 n 个交易日。

    Args:
        d: 参考日期
        calendar: 日历服务
        n: 向前追溯的交易日数量

    Returns:
        目标交易日日期
    """
    days = 0
    cur = d
    while days < n:
        cur = cur - timedelta(days=1)
        if calendar.is_open("CN_A", cur):
            days += 1
    return cur


def main() -> None:
    """
    初始化开发用 SQLite 数据。

    行为：可通过环境变量控制重置与自动确认。
    """
    helper = DbHelper()
    helper.init_schema_if_needed()
    conn = helper.get_connection()

    # 可选：重置核心表，避免历史数据干扰
    reset = os.getenv("SEED_RESET", "1") == "1"
    if reset:
        # 查询已存在的表
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('trades', 'navs', 'funds', 'dca_plans', 'alloc_config', 'trading_calendar')"
        )
        existing_tables = {row[0] for row in cursor.fetchall()}

        with conn:
            for table in existing_tables:
                conn.execute(f"DELETE FROM {table}")
        print(f"[DevSeed] 已重置核心表数据：{', '.join(sorted(existing_tables))}")

    # 填充基础交易日历（开发用简化版）
    today = date.today()
    _seed_basic_calendar(conn, today, days_back=30)

    # 初始化仓储和服务
    fund_repo = FundRepo(conn)
    calendar = CalendarService(conn)
    trade_repo = TradeRepo(conn, calendar)
    nav_repo = NavRepo(conn)
    _ = DcaPlanRepo(conn)  # dca_repo 用于初始化表结构，不在脚本中直接使用
    alloc_repo = AllocConfigRepo(conn)

    # Seed funds（幂等）
    fund_repo.add("110022", "易方达沪深300ETF联接", AssetClass.CSI300, "CN_A")
    fund_repo.add("000001", "华夏大盘精选", AssetClass.CSI300, "CN_A")
    fund_repo.add("162411", "华宝标普美国消费", AssetClass.US_QDII, "US_NYSE")
    print("[DevSeed] 已添加 3 只测试基金")

    # Seed DCA plan
    with conn:
        conn.execute(
            """
            INSERT INTO dca_plans(fund_code, amount, frequency, rule)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(fund_code) DO UPDATE SET
                amount=excluded.amount,
                frequency=excluded.frequency,
                rule=excluded.rule
            """,
            ("110022", "1000", "weekly", "MON"),
        )
    print("[DevSeed] 已添加定投计划：110022 每周1000元")

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
    print("[DevSeed] 已设置资产配置目标权重")

    # 日期选择：A 股示例用"前一交易日"为交易日，使 confirm_date = 今天（T+1）
    trade_day_a = _prev_business_day(today, calendar, n=1)

    # 计算定价日和确认日（使用策略）
    policy = default_policy("CN_A")
    pricing_date, confirm_date = calc_settlement_dates(trade_day_a, policy, calendar)

    # Seed NAV：
    # - 定价日 NAV（用于确认份额）
    # - 当日 NAV（用于市值视图 status/日报）
    nav_repo.upsert("110022", pricing_date, Decimal("1.2000"))
    nav_repo.upsert("110022", today, Decimal("1.2345"))
    nav_repo.upsert("000001", today, Decimal("0.9876"))
    nav_repo.upsert("162411", today, Decimal("0.8765"))
    print(f"[DevSeed] 已添加 NAV 数据（定价日={pricing_date}, 今日={today}）")

    # Create a sample trade（A 股，交易日=前一交易日，今天应确认）
    trade = Trade(
        id=None,
        fund_code="110022",
        type="buy",
        amount=Decimal("1000"),
        trade_date=trade_day_a,
        status="pending",
        market="CN_A",
    )
    saved = trade_repo.add(trade)
    print(
        f"[DevSeed] 已创建交易: id={saved.id}, "
        f"trade_date={trade_day_a}, pricing_date={saved.pricing_date}, "
        f"confirm_date={saved.confirm_date}"
    )

    # Print pending list
    pending = trade_repo.list_pending(confirm_date)
    print(f"[DevSeed] 待确认交易（confirm_date={confirm_date}）: {len(pending)} 笔")

    # 自动执行一次确认（默认开启）
    if os.getenv("SEED_SIMULATE_CONFIRM", "1") == "1":
        result = confirm_trades(today=confirm_date)
        print(
            f"[DevSeed] 确认结果: confirmed={result.confirmed_count}, "
            f"skipped={result.skipped_count}, delayed={result.delayed_count}"
        )

    # v0.2.1: 可选创建"延迟确认"测试场景
    if os.getenv("SEED_CREATE_DELAYED_TRADE", "0") == "1":
        delayed_trade_day = _prev_business_day(today, calendar, n=3)
        delayed_trade = Trade(
            id=None,
            fund_code="162411",
            type="buy",
            amount=Decimal("500"),
            trade_date=delayed_trade_day,
            status="pending",
            market="US_NYSE",
        )
        saved_delayed = trade_repo.add(delayed_trade)
        print(
            f"[DevSeed] 已创建延迟测试交易: id={saved_delayed.id}, "
            f"fund_code=162411, trade_date={delayed_trade_day}"
        )
        print("[DevSeed] 注意：未为该基金添加定价日 NAV，确认时将被标记为延迟")

    # 打印当前状态
    positions = trade_repo.get_position()
    print(f"[DevSeed] 当前持仓: {dict(positions)}")

    target_weights = alloc_repo.get_target_weights()
    print(f"[DevSeed] 目标权重: {dict(target_weights)}")

    print("\n✅ 开发数据初始化完成！")
    print("提示：这是简化的测试数据，生产环境请使用 sync_calendar/patch_calendar 维护日历")


if __name__ == "__main__":
    main()
