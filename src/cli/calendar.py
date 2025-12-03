from __future__ import annotations

import argparse
import sys
from datetime import date

from src.core.log import log
from src.flows.calendar import (
    patch_cn_a_calendar,
    refresh_calendar,
    sync_calendar,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli.calendar",
        description="交易日历管理：CSV 刷新 / exchange_calendars 同步 / Akshare 修补",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="子命令")

    # ========== refresh 子命令 ==========
    refresh_parser = subparsers.add_parser("refresh", help="从 CSV 刷新交易日历")
    refresh_parser.add_argument(
        "--csv",
        required=True,
        help="CSV 文件路径（格式：market,day,is_trading_day 或 day,is_trading_day）",
    )

    # ========== sync 子命令 ==========
    sync_parser = subparsers.add_parser(
        "sync",
        help="使用 exchange_calendars 同步交易日历（注油，全量或区间）",
    )
    sync_parser.add_argument(
        "--market",
        required=True,
        help="市场标识，如 CN_A 或 US_NYSE",
    )
    sync_parser.add_argument(
        "--from",
        dest="since",
        required=True,
        help="起始日 YYYY-MM-DD",
    )
    sync_parser.add_argument(
        "--to",
        dest="until",
        required=True,
        help="截止日 YYYY-MM-DD（含）",
    )

    # ========== patch-cn-a 子命令 ==========
    patch_parser = subparsers.add_parser(
        "patch-cn-a",
        help="使用 Akshare 修补 A 股（CN_A）日历",
    )
    patch_parser.add_argument(
        "--back",
        type=int,
        default=30,
        help="向前修补天数（默认 30）",
    )
    patch_parser.add_argument(
        "--forward",
        type=int,
        default=365,
        help="向后修补天数（默认 365）",
    )

    return parser.parse_args()


def _do_refresh(args: argparse.Namespace) -> int:
    """执行 refresh 命令。"""
    try:
        # 1. 从 CSV 刷新日历
        csv_path = args.csv
        log(f"[Calendar:refresh] 从 CSV 刷新日历：{csv_path}")
        result = refresh_calendar(csv_path=csv_path)

        # 2. 输出结果
        log(
            "✅ 日历刷新成功："
            f"total_days={result.total_days}, updated_days={result.updated_days}"
        )
        return 0
    except FileNotFoundError as err:
        log(f"❌ 文件不存在：{err}")
        return 4
    except ValueError as err:
        log(f"❌ CSV 格式错误：{err}")
        return 4
    except Exception as err:  # noqa: BLE001
        log(f"❌ 刷新日历失败：{err}")
        return 5


def _do_sync(args: argparse.Namespace) -> int:
    """执行 sync 命令（使用 exchange_calendars 注油）。"""
    try:
        # 1. 解析参数
        market = args.market
        start = date.fromisoformat(args.since)
        end = date.fromisoformat(args.until)

        # 2. 同步日历
        log(f"[Calendar:sync] 同步日历：market={market} {start}..{end}")
        result = sync_calendar(market=market, start=start, end=end)

        # 3. 输出结果
        log(
            "✅ 日历同步完成："
            f"total_days={result.total_days}, updated_days={result.updated_days}, "
            f"open_days={result.open_days}"
        )
        return 0
    except ValueError as err:
        log(f"❌ 参数错误：{err}")
        return 4
    except Exception as err:  # noqa: BLE001
        log(f"❌ 日历同步失败：{err}")
        return 5


def _do_patch_cn_a(args: argparse.Namespace) -> int:
    """执行 patch-cn-a 命令（使用 Akshare 修补 CN_A）。"""
    try:
        # 1. 解析参数
        back = int(args.back)
        forward = int(args.forward)

        # 2. 修补日历
        log(
            "[Calendar:patch] 使用 Akshare 修补 CN_A 日历："
            f"back={back} days, forward={forward} days"
        )
        result = patch_cn_a_calendar(
            lookback_days=back,
            forward_days=forward,
        )

        # 3. 输出结果
        if result.total_days == 0:
            log(
                "✅ 日历无需要修补的变更："
                f"范围={result.start_date} -> {result.end_date}"
            )
        else:
            log(
                "✅ A 股日历修补完成："
                f"范围={result.start_date} -> {result.end_date}，"
                f"补修天数={result.update_days}，新增天数={result.insert_days}"
            )
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 修补日历失败：{err}")
        return 5


def main() -> int:
    """
    交易日历管理 CLI。

    Returns:
        退出码：0=成功；4=参数错误；5=其他失败。
    """
    # 1. 解析参数
    args = _parse_args()

    # 2. 路由到子命令
    if args.command == "refresh":
        return _do_refresh(args)
    if args.command == "sync":
        return _do_sync(args)
    if args.command == "patch-cn-a":
        return _do_patch_cn_a(args)

    log(f"❌ 未知命令：{args.command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
