from __future__ import annotations

import argparse
import sys
from datetime import date

from src.core.log import log
from src.flows.dca import run_daily_dca, skip_dca


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli.dca",
        description="定投执行管理（v0.4）",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="子命令")

    # ========== run 子命令 ==========
    run_parser = subparsers.add_parser("run", help="执行当日定投（生成 pending 交易）")
    run_parser.add_argument(
        "--date",
        help="执行日期（YYYY-MM-DD，默认今天）",
    )

    # ========== skip 子命令 ==========
    skip_parser = subparsers.add_parser("skip", help="跳过某日定投")
    skip_parser.add_argument("--fund", required=True, help="基金代码")
    skip_parser.add_argument(
        "--date",
        help="跳过日期（YYYY-MM-DD，默认今天）",
    )
    skip_parser.add_argument("--note", help="跳过原因")

    return parser.parse_args()


def _do_run(args: argparse.Namespace) -> int:
    """执行 run 命令。"""
    try:
        # 1. 解析日期参数
        date_arg = args.date
        today = date.fromisoformat(date_arg) if date_arg else date.today()

        # 2. 执行定投
        log(f"[DCA:run] 开始：date={today}")
        count = run_daily_dca(today=today)
        log(f"✅ 成功生成 {count} 笔定投交易")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 执行失败：{err}")
        return 5


def _do_skip(args: argparse.Namespace) -> int:
    """执行 skip 命令。"""
    try:
        # 1. 解析参数
        fund_code = args.fund
        date_arg = args.date
        day = date.fromisoformat(date_arg) if date_arg else date.today()
        note = args.note

        # 2. 执行跳过操作
        log(f"[DCA:skip] 跳过定投：{fund_code} @ {day}")
        affected = skip_dca(fund_code=fund_code, day=day, note=note)

        # 3. 输出结果
        if affected > 0:
            log(f"✅ 已跳过 {affected} 笔定投交易")
        else:
            log("⚠️ 未找到可跳过的定投交易（可能已执行或不存在）")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 跳过失败：{err}")
        return 5


def main() -> int:
    """
    定投执行管理 CLI（v0.4）。

    Returns:
        退出码：0=成功；5=执行失败。
    """
    # 1. 解析参数
    args = _parse_args()

    # 2. 路由到子命令
    if args.command == "run":
        return _do_run(args)
    elif args.command == "skip":
        return _do_skip(args)
    else:
        log(f"❌ 未知命令：{args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
