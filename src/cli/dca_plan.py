from __future__ import annotations

import argparse
import sys
from decimal import Decimal

from src.core.log import log
from src.flows.config import (
    add_dca_plan,
    delete_dca_plan,
    disable_dca_plan,
    enable_dca_plan,
    list_dca_plans,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli.dca_plan",
        description="定投计划管理（v0.3.2）",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="子命令")

    # ========== add 子命令 ==========
    add_parser = subparsers.add_parser("add", help="添加或更新定投计划")
    add_parser.add_argument("--fund", required=True, help="基金代码")
    add_parser.add_argument("--amount", required=True, type=Decimal, help="定投金额")
    add_parser.add_argument(
        "--freq",
        required=True,
        choices=["daily", "weekly", "monthly"],
        help="定投频率",
    )
    add_parser.add_argument(
        "--rule",
        required=True,
        help="定投规则（daily=空，weekly=MON/TUE/...，monthly=1..31）",
    )
    add_parser.add_argument(
        "--status",
        choices=["active", "disabled"],
        default="active",
        help="状态（默认 active）",
    )

    # ========== list 子命令 ==========
    list_parser = subparsers.add_parser("list", help="列出定投计划")
    list_parser.add_argument(
        "--active-only",
        action="store_true",
        help="仅显示活跃计划",
    )

    # ========== disable 子命令 ==========
    disable_parser = subparsers.add_parser("disable", help="禁用定投计划")
    disable_parser.add_argument("--fund", required=True, help="基金代码")

    # ========== enable 子命令 ==========
    enable_parser = subparsers.add_parser("enable", help="启用定投计划")
    enable_parser.add_argument("--fund", required=True, help="基金代码")

    # ========== delete 子命令 ==========
    delete_parser = subparsers.add_parser("delete", help="删除定投计划")
    delete_parser.add_argument("--fund", required=True, help="基金代码")

    return parser.parse_args()


def _do_add(args: argparse.Namespace) -> int:
    """执行 add 命令。"""
    try:
        # 1. 解析参数
        fund_code = args.fund
        amount = args.amount
        frequency = args.freq
        rule = args.rule
        status = args.status

        # 2. 添加定投计划
        log(f"[DCA:add] 添加定投计划：{fund_code} - {amount} 元/{frequency}/{rule} ({status})")
        add_dca_plan(
            fund_code=fund_code,
            amount=amount,
            frequency=frequency,
            rule=rule,
            status=status,
        )
        log(f"✅ 定投计划 {fund_code} 添加成功")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 添加定投计划失败：{err}")
        return 5


def _do_list(args: argparse.Namespace) -> int:
    """执行 list 命令。"""
    try:
        # 1. 查询定投计划
        active_only = args.active_only
        log(f"[DCA:list] 查询定投计划（active_only={active_only}）")
        plans = list_dca_plans(active_only=active_only)

        if not plans:
            log("（无定投计划）")
            return 0

        # 2. 格式化输出
        log(f"共 {len(plans)} 个定投计划：")
        for plan in plans:
            status_icon = "✅" if plan.status == "active" else "⏸️"
            log(
                f"  {status_icon} {plan.fund_code} | {plan.amount} 元/{plan.frequency}/{plan.rule} | {plan.status}"
            )
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 查询定投计划失败：{err}")
        return 5


def _do_disable(args: argparse.Namespace) -> int:
    """执行 disable 命令。"""
    try:
        # 1. 解析参数
        fund_code = args.fund

        # 2. 禁用定投计划
        log(f"[DCA:disable] 禁用定投计划：{fund_code}")
        disable_dca_plan(fund_code=fund_code)
        log(f"✅ 定投计划 {fund_code} 已禁用")
        return 0
    except ValueError as err:
        log(f"❌ 禁用失败：{err}")
        return 4
    except Exception as err:  # noqa: BLE001
        log(f"❌ 禁用定投计划失败：{err}")
        return 5


def _do_enable(args: argparse.Namespace) -> int:
    """执行 enable 命令。"""
    try:
        # 1. 解析参数
        fund_code = args.fund

        # 2. 启用定投计划
        log(f"[DCA:enable] 启用定投计划：{fund_code}")
        enable_dca_plan(fund_code=fund_code)
        log(f"✅ 定投计划 {fund_code} 已启用")
        return 0
    except ValueError as err:
        log(f"❌ 启用失败：{err}")
        return 4
    except Exception as err:  # noqa: BLE001
        log(f"❌ 启用定投计划失败：{err}")
        return 5


def _do_delete(args: argparse.Namespace) -> int:
    """执行 delete 命令。"""
    try:
        # 1. 解析参数
        fund_code = args.fund

        # 2. 删除定投计划
        log(f"[DCA:delete] 删除定投计划：{fund_code}")
        delete_dca_plan(fund_code=fund_code)
        log(f"✅ 定投计划 {fund_code} 已删除")
        return 0
    except ValueError as err:
        log(f"❌ 删除失败：{err}")
        return 4
    except Exception as err:  # noqa: BLE001
        log(f"❌ 删除定投计划失败：{err}")
        return 5


def main() -> int:
    """
    定投计划管理 CLI（v0.3.4）。

    Returns:
        退出码：0=成功；4=计划不存在；5=其他失败。
    """
    # 1. 解析参数
    args = _parse_args()

    # 2. 路由到子命令
    if args.command == "add":
        return _do_add(args)
    elif args.command == "list":
        return _do_list(args)
    elif args.command == "disable":
        return _do_disable(args)
    elif args.command == "enable":
        return _do_enable(args)
    elif args.command == "delete":
        return _do_delete(args)
    else:
        log(f"❌ 未知命令：{args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
