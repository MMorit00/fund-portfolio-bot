from __future__ import annotations

import argparse
import sys
from datetime import date

from src.core.log import log
from src.data.client.local_nav import LocalNavService
from src.data.db.calendar import CalendarService
from src.data.db.db_helper import DbHelper
from src.data.db.nav_repo import NavRepo
from src.data.db.trade_repo import TradeRepo
from src.flows.trade import ConfirmResult, ConfirmTrades


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.jobs.confirm_trades",
        description="确认到期 pending 交易，可指定确认日",
    )
    parser.add_argument(
        "--day",
        help="确认日（YYYY-MM-DD，默认今天）",
    )
    return parser.parse_args()


def _parse_day(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"日期格式无效：{value}（期望：YYYY-MM-DD）") from exc


def confirm_trades_flow(day: date) -> ConfirmResult:
    """
    确认交易业务流程函数。

    该函数封装了确认交易的完整流程：
    1. 初始化数据库连接和依赖
    2. 调用确认交易用例
    3. 返回确认结果

    Args:
        day: 确认日期

    Returns:
        确认结果统计（confirmed_count / delayed_count / skipped_count）
    """
    # 初始化数据库
    db_helper = DbHelper()
    db_helper.init_schema_if_needed()
    conn = db_helper.get_connection()

    # 构造依赖
    calendar = CalendarService(conn)
    trade_repo = TradeRepo(conn, calendar)
    nav_repo = NavRepo(conn)
    nav_service = LocalNavService(nav_repo)

    # 执行业务逻辑
    usecase = ConfirmTrades(trade_repo, nav_service)
    return usecase.execute(today=day)


def main() -> int:
    """
    确认交易任务入口：按 v0.2.1 规则与 DB 预写确认日确认当日交易。

    Returns:
        退出码：0=成功；5=未知错误。
    """
    try:
        args = _parse_args()
        day = _parse_day(getattr(args, "day", None))
        log(f"[Job] confirm_trades 开始：day={day}")

        result = confirm_trades_flow(day)

        # 构造输出信息（区分"未到期跳过"与"超期延迟"）
        parts = [f"✅ 成功确认 {result.confirmed_count} 笔交易"]

        if result.skipped_count > 0:
            funds_str = ", ".join(result.skipped_funds) if result.skipped_funds else "无"
            parts.append(f"NAV 缺失暂跳过 {result.skipped_count} 笔（未到确认日），基金：{funds_str}")

        if result.delayed_count > 0:
            parts.append(f"标记为延迟 {result.delayed_count} 笔（已超期但 NAV 缺失）")

        log("；".join(parts))

        log("[Job] confirm_trades 结束")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 执行失败：confirm_trades - {err}")
        return 5


if __name__ == "__main__":
    sys.exit(main())
