"""日报生成与发送 CLI。"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from src.core.log import log
from src.flows.report import send_daily_report


def _parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        prog="python -m src.cli.report",
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


def _do_report(args: argparse.Namespace) -> int:
    """执行日报命令。

    Args:
        args: 命令行参数。

    Returns:
        退出码：0=成功；4=参数错误；5=其他失败。
    """
    try:
        # 1. 解析参数
        mode = getattr(args, "mode", "market")
        as_of_arg = getattr(args, "as_of", None)
        as_of = date.fromisoformat(as_of_arg) if as_of_arg else None

        # 2. 输出操作提示
        log(f"[Job:report] 开始：as_of={as_of or '上一交易日'}, mode={mode}")

        # 3. 调用 Flow 函数
        success = send_daily_report(mode=mode, as_of=as_of)

        # 4. 输出结果
        if success:
            log("✅ 日报发送成功")
        else:
            log("⚠️ 日报发送失败（可能未配置 Webhook）")

        log("[Job:report] 结束")
        return 0
    except ValueError as err:
        log(f"❌ 参数错误：{err}")
        return 4
    except Exception as err:  # noqa: BLE001
        log(f"❌ 执行失败：report - {err}")
        return 5


def main() -> int:
    """
    日报任务入口：构建并发送市值视图日报。

    Returns:
        退出码：0=成功；4=参数错误；5=其他失败。
    """
    # 1. 解析参数
    args = _parse_args()

    # 2. 执行日报
    return _do_report(args)


if __name__ == "__main__":
    sys.exit(main())
