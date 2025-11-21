from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

from src.core.log import log
from src.data.client.eastmoney import EastmoneyNavService
from src.data.db.db_helper import DbHelper
from src.data.db.fund_repo import FundRepo
from src.data.db.nav_repo import NavRepo
from src.flows.market import FetchNavs, FetchNavsResult


def _parse_date(value: str | None) -> date:
    if not value:
        raise ValueError("必须提供日期参数，格式 YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"日期格式无效：{value}（期望：YYYY-MM-DD）") from exc


def _daterange(start: date, end: date):
    """包含端点的日期区间生成器。"""
    step = timedelta(days=1)
    d = start
    while d <= end:
        yield d
        d += step


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.jobs.fetch_navs_range",
        description="批量抓取区间内每日的官方净值（严格：仅抓指定日，不回退）",
    )
    parser.add_argument("--from", dest="date_from", required=True, help="开始日期（YYYY-MM-DD）")
    parser.add_argument("--to", dest="date_to", required=True, help="结束日期（YYYY-MM-DD）")
    return parser.parse_args()


def fetch_navs_range_flow(start: date, end: date) -> tuple[int, int, int, dict[str, list[date]]]:
    """
    批量抓取区间内每日净值的业务流程函数。

    该函数封装了批量抓取的完整流程：
    1. 初始化数据库连接和依赖
    2. 遍历日期区间调用 FetchNavs 用例
    3. 汇总结果

    Args:
        start: 开始日期
        end: 结束日期

    Returns:
        元组：(总天数, 最大基金数, 总成功数, 失败汇总字典)
    """
    # 初始化数据库
    db_helper = DbHelper()
    db_helper.init_schema_if_needed()
    conn = db_helper.get_connection()

    # 构造依赖
    fund_repo = FundRepo(conn)
    nav_repo = NavRepo(conn)
    nav_service = EastmoneyNavService()

    # 创建用例
    usecase = FetchNavs(fund_repo, nav_repo, nav_service)

    # 执行批量抓取
    total_days = 0
    total_funds = 0
    total_success = 0
    failed_aggregate: dict[str, list[date]] = {}

    for day in _daterange(start, end):
        total_days += 1
        result: FetchNavsResult = usecase.execute(day=day)
        total_funds = max(total_funds, result.total)
        total_success += result.success

        if result.failed_codes:
            for code in result.failed_codes:
                failed_aggregate.setdefault(code, []).append(day)

        failed_count = len(result.failed_codes)
        log(
            f"[Job] fetch_navs_range 逐日：day={day} "
            f"total={result.total} success={result.success} failed={failed_count}"
        )

    return total_days, total_funds, total_success, failed_aggregate


def main() -> int:
    """
    批量抓取任务入口：按日期区间抓取每日官方净值。

    Returns:
        退出码：0=成功；4=未知错误。
    """
    try:
        args = _parse_args()
        start = _parse_date(args.date_from)
        end = _parse_date(args.date_to)
        if end < start:
            start, end = end, start

        log(f"[Job] fetch_navs_range 开始：from={start} to={end}")

        total_days, total_funds, total_success, failed_aggregate = fetch_navs_range_flow(start, end)

        # 汇总输出
        total_failed = len(failed_aggregate)
        log(
            f"[Job] fetch_navs_range 完成：days={total_days} max_total={total_funds} "
            f"total_success={total_success} total_failed_codes={total_failed}"
        )
        if failed_aggregate:
            # 打印每个失败基金的日期列表（数量较多时也足以定位并重试）
            for code, days in sorted(failed_aggregate.items()):
                days_str = ", ".join(d.isoformat() for d in days)
                log(f"失败：{code} -> [{days_str}]")

        log("[Job] fetch_navs_range 结束")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 执行失败：fetch_navs_range - {err}")
        return 4


if __name__ == "__main__":
    sys.exit(main())

