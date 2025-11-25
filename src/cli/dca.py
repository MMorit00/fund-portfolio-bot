from __future__ import annotations

import argparse
import sys
from datetime import date

from src.core.log import log
from src.flows.dca import run_daily_dca


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli.dca",
        description="定投执行（按计划生成交易）",
    )
    parser.add_argument(
        "--date",
        help="执行日期（格式：YYYY-MM-DD，默认今天）",
    )
    return parser.parse_args()


def main() -> int:
    """
    定投生成任务入口：按计划生成当日 pending 交易。

    Returns:
        退出码：0=成功；5=未知错误。
    """
    try:
        args = _parse_args()
        date_arg = getattr(args, "date", None)
        today = date.fromisoformat(date_arg) if date_arg else date.today()

        log(f"[Job:dca] 开始：date={today}")

        # 直接调用 Flow 函数（依赖自动创建）
        count = run_daily_dca(today=today)
        log(f"✅ 成功生成 {count} 笔定投交易")

        log("[Job:dca] 结束")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 执行失败：dca - {err}")
        return 5


if __name__ == "__main__":
    sys.exit(main())
