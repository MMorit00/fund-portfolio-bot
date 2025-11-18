from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

from src.app.log import log
from src.app.wiring import DependencyContainer


def _prev_business_day(ref: date) -> date:
    """上一工作日（仅周末视为非交易日）。"""
    d = ref - timedelta(days=1)
    while d.weekday() >= 5:
        d = d - timedelta(days=1)
    return d


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.jobs.daily_report",
        description="生成并发送日报（默认上一交易日）",
    )
    parser.add_argument(
        "--as-of",
        help="展示日（YYYY-MM-DD），默认上一交易日（按工作日口径）",
    )
    parser.add_argument(
        "--mode",
        choices=["market", "shares"],
        default="market",
        help="视图模式：market=市值视图（默认）、shares=份额视图",
    )
    return parser.parse_args()


def main() -> int:
    """
    日报任务入口：构建并发送市值视图日报。

    Returns:
        退出码：0=成功；5=未知错误。
    """
    try:
        args = _parse_args()
        mode = getattr(args, "mode", "market")
        as_of = (
            date.fromisoformat(getattr(args, "as_of")) if getattr(args, "as_of", None) else _prev_business_day(date.today())
        )

        log(f"[Job] daily_report 开始：as_of={as_of}, mode={mode}")

        with DependencyContainer() as container:
            usecase = container.get_daily_report_usecase()
            success = usecase.send(mode=mode, as_of=as_of)
            if success:
                log("✅ 日报发送成功")
            else:
                log("⚠️ 日报发送失败（可能未配置 Webhook）")

        log("[Job] daily_report 结束")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 执行失败：daily_report - {err}")
        return 5


if __name__ == "__main__":
    sys.exit(main())
