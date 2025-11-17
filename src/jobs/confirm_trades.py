from __future__ import annotations

import sys
from datetime import date
import argparse

from src.app.log import log
from src.app.wiring import DependencyContainer


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.jobs.confirm_trades",
        description="确认到期 pending 交易，可指定确认日",
    )
    parser.add_argument(
        "--day",
        help="确认日（YYYY-MM-DD，默认今天）",
    )
    return parser.parse_args()


def _parse_day(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"日期格式无效：{value}（期望：YYYY-MM-DD）") from exc


def main() -> int:
    """
    确认交易任务入口：按 v0.2 规则与 DB 预写确认日确认当日交易。

    Returns:
        退出码：0=成功；5=未知错误。
    """
    try:
        args = _parse_args()
        day = _parse_day(getattr(args, "day", None))
        log(f"[Job] confirm_trades 开始：day={day}")

        with DependencyContainer() as container:
            usecase = container.get_confirm_pending_trades_usecase()
            result = usecase.execute(today=day)
            log(
                f"✅ 成功确认 {result.confirmed_count} 笔交易；"
                f"因 NAV 缺失跳过 {result.skipped_count} 笔，基金："
                + (", ".join(result.skipped_funds) if result.skipped_funds else "无")
            )

        log("[Job] confirm_trades 结束")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 执行失败：confirm_trades - {err}")
        return 5


if __name__ == "__main__":
    sys.exit(main())
