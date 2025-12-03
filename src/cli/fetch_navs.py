"""基金净值抓取 CLI。

从外部数据源抓取基金净值并落库。

用法：
    # 抓取上一交易日所有基金净值
    python -m src.cli.fetch_navs

    # 抓取指定日期净值
    python -m src.cli.fetch_navs --date 2024-12-01

    # 抓取指定基金净值
    python -m src.cli.fetch_navs --funds 000001,110022

    # 自动检测延迟交易的缺失 NAV 并补抓
    python -m src.cli.fetch_navs --auto-detect-missing --days 30

说明：
- 模式 1（默认）：按指定日期抓取基金 NAV
- 模式 2（--auto-detect-missing）：自动检测延迟交易的缺失 NAV 并补抓
- 落库按 (fund_code, day) 幂等
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from src.core.log import log
from src.flows.nav import fetch_missing_navs, fetch_navs


def _parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        prog="python -m src.cli.fetch_navs",
        description="从外部数据源抓取基金净值并落库",
    )
    parser.add_argument(
        "--date",
        help="目标日期（格式：YYYY-MM-DD，默认上一交易日，因当日NAV通常晚上才公布）",
    )
    parser.add_argument(
        "--funds",
        help="指定基金代码列表（逗号分隔，如：000001,110022），不指定时抓取所有基金",
    )
    parser.add_argument(
        "--auto-detect-missing",
        action="store_true",
        help="自动检测延迟交易的缺失 NAV 并补抓（忽略 --date 和 --funds）",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="--auto-detect-missing 时检测的天数范围（默认 30 天）",
    )
    return parser.parse_args()


def _do_auto_detect(args: argparse.Namespace) -> int:
    """执行自动检测缺失 NAV 模式。

    Args:
        args: 命令行参数。

    Returns:
        退出码：0=成功；5=其他失败。
    """
    # 1. 输出操作提示
    log(f"[FetchNavs] 自动检测模式：扫描最近 {args.days} 天的延迟交易")

    # 2. 调用 Flow 函数
    result = fetch_missing_navs(days=args.days)

    # 3. 输出结果
    log(
        f"[FetchNavs] 补抓结束：total={result.total} "
        f"success={result.success} failed={len(result.failed_codes)}"
    )

    # 4. 输出失败列表
    if result.failed_codes:
        log(
            "[FetchNavs] 补抓失败（部分可能因 NAV 缺失或网络错误）： "
            + ", ".join(sorted(result.failed_codes))
        )

    return 0


def _do_fetch_by_date(args: argparse.Namespace) -> int:
    """执行按日期抓取模式。

    Args:
        args: 命令行参数。

    Returns:
        退出码：0=成功；5=其他失败。
    """
    # 1. 解析参数
    date_arg = getattr(args, "date", None)
    target_day = date.fromisoformat(date_arg) if date_arg else None
    fund_codes = [c.strip() for c in args.funds.split(",") if c.strip()] if args.funds else None

    # 2. 输出操作提示
    log(f"[FetchNavs] 开始：day={target_day or '上一交易日'} funds={fund_codes or '全部'}")

    # 3. 调用 Flow 函数（day=None 时自动使用上一交易日）
    result = fetch_navs(day=target_day, fund_codes=fund_codes)

    # 4. 输出结果
    log(
        f"[FetchNavs] 结束：day={result.day} total={result.total} "
        f"success={result.success} failed={len(result.failed_codes)}"
    )

    # 5. 输出失败列表
    if result.failed_codes:
        log(
            "[FetchNavs] 失败基金代码（部分可能因 NAV 缺失或网络错误）： "
            + ", ".join(sorted(result.failed_codes))
        )
        # 如果抓今日NAV且失败较多，给出友好提示
        if result.day == date.today() and len(result.failed_codes) > result.success:
            log("⚠️  提示：今日 NAV 可能尚未公布（通常 18:00-22:00 后可抓取），建议晚上重试")

    return 0


def main() -> int:
    """
    抓取净值任务入口。

    Returns:
        退出码：0=成功；4=参数错误；5=其他失败。
    """
    try:
        # 1. 解析参数
        args = _parse_args()

        # 2. 路由执行
        if args.auto_detect_missing:
            return _do_auto_detect(args)
        else:
            return _do_fetch_by_date(args)

    except ValueError as err:
        log(f"❌ 参数错误：{err}")
        return 4
    except Exception as err:  # noqa: BLE001
        log(f"❌ 执行失败：{err}")
        return 5


if __name__ == "__main__":
    sys.exit(main())
