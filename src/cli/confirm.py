"""交易确认 CLI。

按确认规则与 DB 预写确认日确认当日交易。

用法：
    # 确认今天的交易
    python -m src.cli.confirm

    # 确认指定日期的交易
    python -m src.cli.confirm --day 2024-01-15
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from src.core.log import log
from src.flows.trade import ConfirmResult, confirm_trades


def _parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        prog="python -m src.cli.confirm",
        description="确认到期 pending 交易，可指定确认日",
    )
    parser.add_argument(
        "--day",
        help="确认日（YYYY-MM-DD，默认今天）",
    )
    return parser.parse_args()


def _format_result(result: ConfirmResult) -> None:
    """格式化并输出确认结果。

    Args:
        result: 确认结果。
    """
    # 1. 构造输出信息（区分"未到期跳过"与"超期延迟"）
    parts = [f"✅ 成功确认 {result.confirmed_count} 笔交易"]

    # 2. 添加 NAV 缺失跳过信息
    if result.skipped_count > 0:
        funds_str = ", ".join(result.skipped_funds) if result.skipped_funds else "无"
        parts.append(f"NAV 缺失暂跳过 {result.skipped_count} 笔（未到确认日），基金：{funds_str}")

    # 3. 添加延迟标记信息
    if result.delayed_count > 0:
        parts.append(f"标记为延迟 {result.delayed_count} 笔（已超期但 NAV 缺失）")

    # 4. 输出结果
    log("；".join(parts))


def _do_confirm(args: argparse.Namespace) -> int:
    """执行确认命令。

    Args:
        args: 命令行参数。

    Returns:
        退出码：0=成功；5=未知错误。
    """
    try:
        # 1. 解析日期参数
        day_arg = getattr(args, "day", None)
        day = date.fromisoformat(day_arg) if day_arg else date.today()
        log(f"[Job:confirm] 开始：day={day}")

        # 2. 调用 Flow 函数
        result = confirm_trades(today=day)

        # 3. 格式化输出
        _format_result(result)

        # 4. 输出完成信息
        log("[Job:confirm] 结束")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 执行失败：confirm - {err}")
        return 5


def main() -> int:
    """
    确认交易任务入口：按确认规则与 DB 预写确认日确认当日交易。

    Returns:
        退出码：0=成功；5=未知错误。
    """
    # 1. 解析参数
    args = _parse_args()

    # 2. 执行确认
    return _do_confirm(args)


if __name__ == "__main__":
    sys.exit(main())
