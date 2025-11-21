from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

from src.core.log import log
from src.data.client.discord import DiscordReportService
from src.data.client.local_nav import LocalNavService
from src.data.db.alloc_config_repo import AllocConfigRepo
from src.data.db.calendar import CalendarService
from src.data.db.db_helper import DbHelper
from src.data.db.fund_repo import FundRepo
from src.data.db.nav_repo import NavRepo
from src.data.db.trade_repo import TradeRepo
from src.flows.report import MakeDailyReport


def _prev_business_day(ref: date) -> date:
    """上一工作日（仅周末视为非交易日）。"""
    d = ref - timedelta(days=1)
    while d.weekday() >= 5:
        d = d - timedelta(days=1)
    return d


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.jobs.daily_report",
        description="生成并发送日报（默认上一交易日）",
    )
    parser.add_argument(
        "--as-of",
        help="展示日（YYYY-MM-DD），默认上一交易日（按工作日口径）",
    )
    parser.add_argument(
        "--mode",
        choices=["market", "shares"],
        default="market",
        help="视图模式：market=市值视图（默认）、shares=份额视图",
    )
    return parser.parse_args()


def daily_report_flow(mode: str, as_of: date) -> bool:
    """
    日报生成业务流程函数。

    该函数封装了日报生成的完整流程：
    1. 初始化数据库连接和依赖
    2. 调用日报生成用例
    3. 返回发送结果

    Args:
        mode: 视图模式（market/shares）
        as_of: 展示日期

    Returns:
        是否发送成功
    """
    # 初始化数据库
    db_helper = DbHelper()
    db_helper.init_schema_if_needed()
    conn = db_helper.get_connection()

    # 构造依赖
    calendar = CalendarService(conn)
    alloc_repo = AllocConfigRepo(conn)
    trade_repo = TradeRepo(conn, calendar)
    fund_repo = FundRepo(conn)
    nav_repo = NavRepo(conn)
    nav_service = LocalNavService(nav_repo)
    report_service = DiscordReportService()

    # 执行业务逻辑
    usecase = MakeDailyReport(alloc_repo, trade_repo, fund_repo, nav_service, report_service)
    return usecase.send(mode=mode, as_of=as_of)


def main() -> int:
    """
    日报任务入口：构建并发送市值视图日报。

    Returns:
        退出码：0=成功；5=未知错误。
    """
    try:
        args = _parse_args()
        mode = getattr(args, "mode", "market")
        as_of_arg = getattr(args, "as_of", None)
        as_of = (
            date.fromisoformat(as_of_arg)
            if as_of_arg
            else _prev_business_day(date.today())
        )

        log(f"[Job] daily_report 开始：as_of={as_of}, mode={mode}")

        success = daily_report_flow(mode, as_of)
        if success:
            log("✅ 日报发送成功")
        else:
            log("⚠️ 日报发送失败（可能未配置 Webhook）")

        log("[Job] daily_report 结束")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 执行失败：daily_report - {err}")
        return 5


if __name__ == "__main__":
    sys.exit(main())
