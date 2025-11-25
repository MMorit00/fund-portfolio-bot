from __future__ import annotations

import argparse
import sys
from datetime import date

from src.core.log import log
from src.flows.trade import confirm_trades


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli.confirm",
        description="确认到期 pending 交易，可指定确认日",
    )
    parser.add_argument(
        "--day",
        help="确认日（YYYY-MM-DD，默认今天）",
    )
    return parser.parse_args()


def main() -> int:
    """
    确认交易任务入口：按确认规则与 DB 预写确认日确认当日交易。

    Returns:
        退出码：0=成功；5=未知错误。
    """
    try:
        args = _parse_args()
        day_arg = getattr(args, "day", None)
        day = date.fromisoformat(day_arg) if day_arg else date.today()
        log(f"[Job:confirm] 开始：day={day}")

        # 直接调用 Flow 函数（依赖自动创建）
        result = confirm_trades(today=day)

        # 构造输出信息（区分"未到期跳过"与"超期延迟"）
        parts = [f"✅ 成功确认 {result.confirmed_count} 笔交易"]

        if result.skipped_count > 0:
            funds_str = ", ".join(result.skipped_funds) if result.skipped_funds else "无"
            parts.append(f"NAV 缺失暂跳过 {result.skipped_count} 笔（未到确认日），基金：{funds_str}")

        if result.delayed_count > 0:
            parts.append(f"标记为延迟 {result.delayed_count} 笔（已超期但 NAV 缺失）")

        log("；".join(parts))

        log("[Job:confirm] 结束")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 执行失败：confirm - {err}")
        return 5


if __name__ == "__main__":
    sys.exit(main())
