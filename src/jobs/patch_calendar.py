from __future__ import annotations

import os
import sqlite3
from datetime import date, timedelta

import akshare as ak
import pandas as pd

from src.app.log import log

"""
日历修补匠 (Patch Calendar) - Akshare 版

职责：从新浪财经拉取最新的 A 股交易日历，覆盖本地数据库。
频率：建议每周运行一次，或每年 12 月密集运行。
"""


def _ensure_table(conn: sqlite3.Connection) -> None:
    # 确保表存在（和 sync_calendar 保持一致）
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


def patch_cn_a() -> None:
    log("[Patch] 正在从新浪财经(Akshare)拉取最新 A 股日历...")

    try:
        # 1) 获取交易日历（返回一列 trade_date，均为交易日）
        df = ak.tool_trade_date_hist_sina()

        # 转换为日期集合
        trade_dates = set(pd.to_datetime(df["trade_date"]).dt.date)

        # 2) 修补范围：过去 30 天 ~ 未来 365 天，且不超过数据源最大已知日期
        today = date.today()
        start_date = today - timedelta(days=30)
        max_remote_date = max(trade_dates)
        log(f"[Patch] 数据源最大已知日期: {max_remote_date}")
        target_end_date = today + timedelta(days=365)
        end_date = min(target_end_date, max_remote_date)
        if end_date < start_date:
            log("[Patch] ⚠️ 数据源数据过旧，无需修补（end_date < start_date）")
            return

        rows: list[tuple[str, str, int]] = []
        total_days = (end_date - start_date).days + 1
        for i in range(total_days):
            current = start_date + timedelta(days=i)
            is_trading = 1 if current in trade_dates else 0
            rows.append(("CN_A", current.isoformat(), is_trading))

        # 3) Upsert 覆盖数据库
        db_path = os.getenv("DB_PATH", "data/portfolio.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        try:
            _ensure_table(conn)
            # 3.1) 统计“补修”与“新增”
            existing_rows = conn.execute(
                """
                SELECT day, is_trading_day
                FROM trading_calendar
                WHERE market = ? AND day BETWEEN ? AND ?
                """,
                ("CN_A", start_date.isoformat(), end_date.isoformat()),
            ).fetchall()
            existing: dict[str, int] = {str(r[0]): int(r[1]) for r in existing_rows}
            inserts = 0
            patches = 0
            for _m, day, val in rows:
                old = existing.get(day)
                if old is None:
                    inserts += 1
                elif old != val:
                    patches += 1

            with conn:
                conn.executemany(
                    """
                    INSERT INTO trading_calendar(market, day, is_trading_day)
                    VALUES (?, ?, ?)
                    ON CONFLICT(market, day) DO UPDATE SET is_trading_day=excluded.is_trading_day
                    """,
                    rows,
                )
            if patches == 0 and inserts == 0:
                log(f"[Patch] ✅ 无补修：日历一致（范围：{start_date} -> {end_date}）")
            else:
                log(
                    f"[Patch] ✅ A股日历修补完成！范围：{start_date} -> {end_date}\n"
                    f"        补修天数：{patches}，新增天数：{inserts}"
                )
        finally:
            conn.close()

    except Exception as e:  # noqa: BLE001
        log(f"[Patch] ❌ Akshare 拉取失败（可能是网络或源站波动）: {e}")
        # 容错：不抛出异常，主程序继续运行，下次再试


def main() -> None:
    # 目前只支持修补 A 股，美股 exchange_calendars 足够准
    patch_cn_a()


if __name__ == "__main__":
    main()
