"""日历数据管理相关业务流程。"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from src.core.dependency import dependency
from src.core.log import log
from src.data.db.db_helper import DbHelper


@dataclass(slots=True)
class RefreshCalendarResult:
    """日历刷新结果统计。"""

    total_rows: int
    affected_rows: int


@dataclass(slots=True)
class SyncCalendarResult:
    """日历同步结果统计。"""

    total_rows: int
    affected_rows: int
    opens: int


@dataclass(slots=True)
class PatchCalendarResult:
    """日历修补结果统计（当前仅支持 CN_A）。"""

    total_rows: int
    inserts: int
    patches: int
    start_date: date
    end_date: date


def _ensure_calendar_table(conn) -> None:
    """确保 trading_calendar 表存在。"""
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


@dependency
def refresh_calendar(
    *,
    csv_path: str,
    db_helper: DbHelper | None = None,
) -> RefreshCalendarResult:
    """
    从 CSV 导入或更新交易日历（v0.3.4 新增）。

    CSV 格式支持：
        1) 完整格式：market,day,is_trading_day
        2) 简化格式：day,is_trading_day（此时 market 默认为 "CN_A"）

    Args:
        csv_path: CSV 文件路径。
        db_helper: 数据库辅助（可选，自动注入）。

    Returns:
        RefreshCalendarResult 包含总行数和实际影响行数。

    Raises:
        FileNotFoundError: CSV 文件不存在。
        ValueError: CSV 格式错误（缺少必需列）。

    副作用：
        - 确保 trading_calendar 表存在；
        - 按 (market, day) 幂等插入或更新日历数据。
    """
    csv_file = Path(csv_path)
    if not csv_file.exists():
        raise FileNotFoundError(f"CSV 文件不存在：{csv_path}")

    conn = db_helper.get_connection()

    # 确保表存在
    _ensure_calendar_table(conn)

    # 读取 CSV
    rows: list[tuple[str, str, int]] = []
    with csv_file.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        if {"market", "day", "is_trading_day"}.issubset(fieldnames):
            # 完整格式
            for r in reader:
                rows.append((r["market"], r["day"], int(r["is_trading_day"])))
        elif {"day", "is_trading_day"}.issubset(fieldnames):
            # 简化格式，默认 market=CN_A
            for r in reader:
                rows.append(("CN_A", r["day"], int(r["is_trading_day"])))
        else:
            raise ValueError("CSV 表头必须包含 day,is_trading_day（可选 market）")

    # 幂等插入
    with conn:
        cur = conn.executemany(
            """
            INSERT INTO trading_calendar(market, day, is_trading_day)
            VALUES (?, ?, ?)
            ON CONFLICT(market, day) DO UPDATE SET is_trading_day=excluded.is_trading_day
            """,
            rows,
        )
        affected = cur.rowcount or 0

    log(f"[Calendar] CSV 导入完成：total={len(rows)} affected={affected}")
    return RefreshCalendarResult(total_rows=len(rows), affected_rows=affected)


def _map_market_to_xc_code(market: str) -> str:
    """
    将本项目的 market 标识映射到 exchange_calendars 代码。

    当前约定：
    - CN_A    → XSHG  （以上交所日历为基准，后续可扩展为并集）
    - US_NYSE → XNYS
    """
    mapping = {
        "CN_A": "XSHG",
        "US_NYSE": "XNYS",
    }
    try:
        return mapping[market]
    except KeyError as exc:  # noqa: PERF203
        raise ValueError(f"未支持的 market: {market}") from exc


@dependency
def sync_calendar(
    *,
    market: str,
    start: date,
    end: date,
    db_helper: DbHelper | None = None,
) -> SyncCalendarResult:
    """
    使用 exchange_calendars 同步指定市场在给定区间内的交易日历。

    设计原则：
        - exchange_calendars 负责提供"注油"数据（基础交易日信息）；
        - 仅覆盖到数据源“最大已知日期”，避免将未知未来误标为休市；
        - 按 (market, day) 幂等 upsert 写入 trading_calendar。

    Args:
        market: 市场标识，如 "CN_A" 或 "US_NYSE"。
        start: 起始日期（含）。
        end: 截止日期（含）。
        db_helper: 数据库辅助（可选，自动注入）。

    Returns:
        SyncCalendarResult：包含总行数 / 受影响行数 / 交易日数量。

    Raises:
        ValueError: 参数错误（如 start > end 或不支持的 market）。
        RuntimeError: exchange_calendars 导入失败等。
    """
    if start > end:
        raise ValueError(f"start 不得晚于 end：start={start}, end={end}")

    try:
        import exchange_calendars as xc  # type: ignore[import]
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "导入 exchange_calendars 失败，请先安装依赖，例如：uv add exchange_calendars"
        ) from exc

    ex_code = _map_market_to_xc_code(market)
    cal = xc.get_calendar(ex_code)
    schedule = cal.schedule.loc[str(start) : str(end)]
    if schedule.empty:
        log(f"[Calendar:sync] ⚠️ exchange_calendars 无数据：market={market} {start}..{end}")
        return SyncCalendarResult(total_rows=0, affected_rows=0, opens=0)

    trading_days_set = set(schedule.index.date)
    max_known = max(trading_days_set)

    # 仅覆盖到“日历已知的最大日期”，防止把未知未来错误写成休市日
    effective_end = min(end, max_known)
    if effective_end < start:
        log(
            f"[Calendar:sync] ⚠️ 有效日期范围为空："
            f"market={market} start={start} effective_end={effective_end}"
        )
        return SyncCalendarResult(total_rows=0, affected_rows=0, opens=0)

    rows: list[tuple[str, str, int]] = []
    total_days = (effective_end - start).days + 1
    for i in range(total_days):
        current = start + timedelta(days=i)
        is_trading = 1 if current in trading_days_set else 0
        rows.append((market, current.isoformat(), is_trading))

    conn = db_helper.get_connection()
    _ensure_calendar_table(conn)

    with conn:
        cur = conn.executemany(
            """
            INSERT INTO trading_calendar(market, day, is_trading_day)
            VALUES (?, ?, ?)
            ON CONFLICT(market, day) DO UPDATE SET is_trading_day=excluded.is_trading_day
            """,
            rows,
        )
        affected = cur.rowcount or 0

    opens = sum(1 for _, _, v in rows if v == 1)
    log(
        f"[Calendar:sync] 同步完成：market={market} "
        f"range={start}..{effective_end} total={len(rows)} opens={opens}"
    )
    return SyncCalendarResult(
        total_rows=len(rows),
        affected_rows=affected,
        opens=opens,
    )


@dependency
def patch_calendar_cn_a(
    *,
    lookback_days: int = 30,
    forward_days: int = 365,
    db_helper: DbHelper | None = None,
) -> PatchCalendarResult:
    """
    使用 Akshare 修补 A 股交易日历（CN_A）。

    策略：
        - 数据源：新浪财经（Akshare tool_trade_date_hist_sina）；
        - 目标区间：today-lookback_days ~ min(today+forward_days, 数据源最大已知日期)；
        - 对该区间内所有日期写入 is_trading_day 标记；
        - 仅统计并 upsert CN_A 市场的数据。

    Args:
        lookback_days: 向前修补天数（默认 30）。
        forward_days: 向后修补天数（默认 365）。
        db_helper: 数据库辅助（可选，自动注入）。

    Returns:
        PatchCalendarResult：包含总天数 / 新增天数 / 补修天数及范围。

    Raises:
        RuntimeError: Akshare 或 pandas 导入失败等。
    """
    try:
        import akshare as ak  # type: ignore[import]
        import pandas as pd  # type: ignore[import]
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "导入 Akshare 或 pandas 失败，请先安装依赖：uv add akshare pandas"
        ) from exc

    log("[Calendar:patch] 正在从新浪财经(Akshare)拉取最新 A 股日历…")

    # 1) 获取交易日列表（全部为交易日）
    df = ak.tool_trade_date_hist_sina()
    if "trade_date" not in df.columns:
        raise RuntimeError("Akshare 返回数据缺少 trade_date 列")

    trade_dates = set(pd.to_datetime(df["trade_date"]).dt.date)
    if not trade_dates:
        raise RuntimeError("Akshare 返回的交易日列表为空")

    # 2) 计算修补区间
    today = date.today()
    start_date = today - timedelta(days=lookback_days)
    max_remote_date = max(trade_dates)
    log(f"[Calendar:patch] 数据源最大已知日期: {max_remote_date}")

    target_end_date = today + timedelta(days=forward_days)
    end_date = min(target_end_date, max_remote_date)
    if end_date < start_date:
        log("[Calendar:patch] ⚠️ 数据源数据过旧，无需修补（end_date < start_date）")
        return PatchCalendarResult(
            total_rows=0,
            inserts=0,
            patches=0,
            start_date=start_date,
            end_date=end_date,
        )

    rows: list[tuple[str, str, int]] = []
    total_days = (end_date - start_date).days + 1
    for i in range(total_days):
        current = start_date + timedelta(days=i)
        is_trading = 1 if current in trade_dates else 0
        rows.append(("CN_A", current.isoformat(), is_trading))

    conn = db_helper.get_connection()
    _ensure_calendar_table(conn)

    # 3) 统计“补修”与“新增”
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
    for _m, day_str, val in rows:
        old = existing.get(day_str)
        if old is None:
            inserts += 1
        elif old != val:
            patches += 1

    with conn:
        cur = conn.executemany(
            """
            INSERT INTO trading_calendar(market, day, is_trading_day)
            VALUES (?, ?, ?)
            ON CONFLICT(market, day) DO UPDATE SET is_trading_day=excluded.is_trading_day
            """,
            rows,
        )
        _ = cur.rowcount or 0

    log(
        f"[Calendar:patch] A 股日历修补完成：范围={start_date} -> {end_date}，"
        f"补修天数={patches}，新增天数={inserts}"
    )
    return PatchCalendarResult(
        total_rows=len(rows),
        inserts=inserts,
        patches=patches,
        start_date=start_date,
        end_date=end_date,
    )
