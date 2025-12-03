"""批量抓取日期区间净值 CLI。

批量抓取区间内每日的官方净值（严格：仅抓指定日，不回退）。

用法：
    # 抓取指定日期区间的净值
    python -m src.cli.fetch_navs_range --from 2024-11-01 --to 2024-11-30

说明：
- 逐日调用 fetch_navs，按日期顺序依次抓取
- 汇总输出总天数、总成功数、失败基金及其失败日期列表
- 适用于补齐历史净值或批量初始化
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

from src.core.log import log
from src.flows.nav import fetch_navs


def _daterange(start: date, end: date):
    """包含端点的日期区间生成器。

    Args:
        start: 开始日期。
        end: 结束日期。

    Yields:
        日期序列（包含端点）。
    """
    step = timedelta(days=1)
    d = start
    while d <= end:
        yield d
        d += step


def _parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        prog="python -m src.cli.fetch_navs_range",
        description="批量抓取区间内每日的官方净值（严格：仅抓指定日，不回退）",
    )
    parser.add_argument("--from", dest="date_from", required=True, help="开始日期（YYYY-MM-DD）")
    parser.add_argument("--to", dest="date_to", required=True, help="结束日期（YYYY-MM-DD）")
    return parser.parse_args()


def _do_range_fetch(start: date, end: date) -> int:
    """执行区间抓取。

    Args:
        start: 开始日期。
        end: 结束日期。

    Returns:
        退出码：0=成功；5=其他失败。
    """
    # 1. 初始化统计变量
    total_days = 0
    total_funds = 0
    total_success = 0
    failed_aggregate: dict[str, list[date]] = {}

    # 2. 输出操作提示
    log(f"[FetchNavsRange] 开始：from={start} to={end}")

    # 3. 逐日抓取
    for day in _daterange(start, end):
        total_days += 1
        result = fetch_navs(day=day)
        total_funds = max(total_funds, result.total)
        total_success += result.success

        # 4. 聚合失败记录
        if result.failed_codes:
            for code_date in result.failed_codes:
                # failed_codes 格式为 "code@date"，提取 code 部分
                code = code_date.split("@")[0]
                failed_aggregate.setdefault(code, []).append(day)

        # 5. 输出逐日结果
        failed_count = len(result.failed_codes)
        log(
            f"[FetchNavsRange] 逐日：day={day} "
            f"total={result.total} success={result.success} failed={failed_count}"
        )

    # 6. 汇总输出
    total_failed = len(failed_aggregate)
    log(
        f"[FetchNavsRange] 完成：days={total_days} max_total={total_funds} "
        f"total_success={total_success} total_failed_codes={total_failed}"
    )

    # 7. 输出失败明细
    if failed_aggregate:
        for code, days in sorted(failed_aggregate.items()):
            days_str = ", ".join(d.isoformat() for d in days)
            log(f"[FetchNavsRange] 失败：{code} -> [{days_str}]")

    log("[FetchNavsRange] 结束")
    return 0


def main() -> int:
    """
    批量抓取任务入口。

    Returns:
        退出码：0=成功；4=参数错误；5=其他失败。
    """
    try:
        # 1. 解析参数
        args = _parse_args()

        # 2. 解析日期并自动排序
        start = date.fromisoformat(args.date_from)
        end = date.fromisoformat(args.date_to)
        if end < start:
            start, end = end, start

        # 3. 执行区间抓取
        return _do_range_fetch(start, end)

    except ValueError as err:
        log(f"❌ 参数错误：{err}")
        return 4
    except Exception as err:  # noqa: BLE001
        log(f"❌ 执行失败：{err}")
        return 5


if __name__ == "__main__":
    sys.exit(main())

