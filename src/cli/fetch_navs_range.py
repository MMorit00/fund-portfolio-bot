from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

from src.core.log import log
from src.flows.nav import fetch_navs


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


def main() -> int:
    """
    批量抓取任务入口：按日期区间抓取每日官方净值。

    Returns:
        退出码：0=成功；4=未知错误。
    """
    try:
        args = _parse_args()
        start = date.fromisoformat(args.date_from)
        end = date.fromisoformat(args.date_to)
        if end < start:
            start, end = end, start

        log(f"[Job:fetch_navs_range] 开始：from={start} to={end}")

        # 执行批量抓取（直接调用 Flow 函数）
        total_days = 0
        total_funds = 0
        total_success = 0
        failed_aggregate: dict[str, list[date]] = {}

        for day in _daterange(start, end):
            total_days += 1
            result = fetch_navs(day=day)
            total_funds = max(total_funds, result.total)
            total_success += result.success

            if result.failed_codes:
                for code_date in result.failed_codes:
                    # failed_codes 格式为 "code@date"，提取 code 部分
                    code = code_date.split("@")[0]
                    failed_aggregate.setdefault(code, []).append(day)

            failed_count = len(result.failed_codes)
            log(
                f"[Job:fetch_navs_range] 逐日：day={day} "
                f"total={result.total} success={result.success} failed={failed_count}"
            )

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

