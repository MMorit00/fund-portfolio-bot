from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import date, timedelta

from src.app.log import log

"""
交易日历同步 Job（骨架）：

职责：
- 使用 `exchange_calendars` 生成指定交易所（如 XNYS / XSHG）的开市日；
- 将结果按 `trading_calendar(calendar_key, day, is_trading_day)` 写入 SQLite。

说明：
- 依赖项 `exchange_calendars` 未在仓库固定安装；请自行 `pip install exchange_calendars` 后使用；
- 也可替换为其他数据源（如 Tushare/Akshare/自维护 CSV）。
"""


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m src.jobs.sync_calendar")
    p.add_argument("--cal", required=True, help="日历键，如 CN_A / US_NYSE")
    p.add_argument("--from", dest="since", required=True, help="起始日 YYYY-MM-DD")
    p.add_argument("--to", dest="until", required=True, help="截止日 YYYY-MM-DD（含）")
    return p.parse_args()


def _map_to_exchange_code(calendar_key: str) -> str:
    """将本仓库的 calendar_key 映射到 exchange_calendars 的代码。"""
    mapping = {
        "CN_A": "XSHG",  # 以上交所为准，后续可并集
        "US_NYSE": "XNYS",
    }
    if calendar_key not in mapping:
        raise ValueError(f"未支持的 calendar_key: {calendar_key}")
    return mapping[calendar_key]


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trading_calendar (
            market TEXT NOT NULL,
            day TEXT NOT NULL,
            is_trading_day INTEGER NOT NULL CHECK(is_trading_day IN (0,1)),
            PRIMARY KEY (market, day)
        )
        """
    )


def _sync_with_xc(cal_key: str, since: date, until: date) -> list[tuple[str, str, int]]:
    """使用 exchange_calendars 生成 (calendar_key, day, is_trading_day) 行。"""
    try:
        import exchange_calendars as xc  # type: ignore
    except Exception as exc:  # noqa: BLE001
        log("请先安装依赖：uv add exchange_calendars")
        raise SystemExit(2) from exc

    ex_code = _map_to_exchange_code(cal_key)
    cal = xc.get_calendar(ex_code)
    schedule = cal.schedule.loc[str(since): str(until)]
    if schedule.empty:
        return []
    trading_days_set = set(schedule.index.date)
    max_known = max(trading_days_set)
    # 仅覆盖到“日历已知的最大日期”，防止把未知未来错误写成 0
    effective_until = min(until, max_known)

    rows: list[tuple[str, str, int]] = []
    total_days = (effective_until - since).days + 1
    for i in range(total_days):
        current = since + timedelta(days=i)
        is_trading = 1 if current in trading_days_set else 0
        rows.append((cal_key, current.isoformat(), is_trading))
    return rows

def main() -> int:
    try:
        args = _parse_args()
        cal_key = args.cal
        since = date.fromisoformat(args.since)
        until = date.fromisoformat(args.until)

        # 仅使用 exchange_calendars 作为注油数据源
        rows = _sync_with_xc(cal_key, since, until)

        db_path = os.getenv("DB_PATH", "data/portfolio.db")
        conn = sqlite3.connect(db_path)
        try:
            _ensure_table(conn)
            with conn:
                conn.executemany(
                    """
                    INSERT INTO trading_calendar(market, day, is_trading_day)
                    VALUES (?, ?, ?)
                    ON CONFLICT(market, day) DO UPDATE SET is_trading_day=excluded.is_trading_day
                    """,
                    rows,
                )
            log(f"[Job:sync_calendar] ✅ 同步完成：{cal_key} {since}..{until}")
            opens = sum(1 for _, _, v in rows if v == 1)
            log(f"   - 总天数: {len(rows)}")
            log(f"   - 交易日: {opens}")
            log(f"   - 休市日: {len(rows) - opens}")
        finally:
            conn.close()
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"[Job:sync_calendar] ❌ 失败：{err}")
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
