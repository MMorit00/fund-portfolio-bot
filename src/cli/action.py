from __future__ import annotations

import argparse
import sys

from src.core.log import log
from src.core.models import ActionLog
from src.flows.config import list_actions


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli.action",
        description="行为日志查询（v0.4.1）",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="子命令")

    # ========== list 子命令 ==========
    list_parser = subparsers.add_parser("list", help="查询最近行为日志")
    list_parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="查询天数（默认 30）",
    )

    return parser.parse_args()


def _format_action(action: ActionLog) -> str:
    """格式化单条行为日志。"""
    # 动作图标
    action_icons = {
        "buy": "📈",
        "sell": "📉",
        "dca_skip": "⏭️",
        "cancel": "❌",
    }
    icon = action_icons.get(action.action, "•")

    # 时间格式化
    time_str = action.acted_at.strftime("%Y-%m-%d %H:%M")

    # 基本信息
    parts = [f"{icon} [{action.id}] {action.action}"]

    # trade_id
    if action.trade_id:
        parts.append(f"trade#{action.trade_id}")

    # intent
    if action.intent:
        parts.append(f"[{action.intent}]")

    # 时间
    parts.append(f"@ {time_str}")

    line = " ".join(parts)

    # note 单独一行
    if action.note:
        line += f"\n       📝 {action.note}"

    return line


def _do_list(args: argparse.Namespace) -> int:
    """执行 list 命令。"""
    try:
        days = args.days
        log(f"[Action:list] 查询最近 {days} 天行为日志")

        actions = list_actions(days=days)

        if not actions:
            log("（无行为记录）")
            return 0

        log(f"共 {len(actions)} 条记录：")
        for action in actions:
            log(f"  {_format_action(action)}")

        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 查询失败：{err}")
        return 5


def main() -> int:
    """
    行为日志查询 CLI（v0.4.1）。

    Returns:
        退出码：0=成功；5=其他失败。
    """
    args = _parse_args()

    if args.command == "list":
        return _do_list(args)
    else:
        log(f"❌ 未知命令：{args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
