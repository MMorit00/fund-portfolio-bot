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
from src.flows.dca_backfill import (
    backfill,
    checks,
    set_core,
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

    # ========== backfill-days 子命令（v0.4.5 AI 驱动）==========
    backfill_days_parser = subparsers.add_parser(
        "backfill-days", help="批量回填指定交易为 DCA 核心（AI 驱动）"
    )
    # 方式1：直接指定 trade IDs（保留，用于特殊情况）
    backfill_days_parser.add_argument(
        "--trade-ids",
        type=str,
        default=None,
        help="交易 ID 列表（逗号分隔）。与 --batch-id 二选一。",
    )
    # 方式2：自动获取（推荐，省 token）
    backfill_days_parser.add_argument(
        "--batch-id",
        type=int,
        default=None,
        help="导入批次 ID。与 --fund/--freq/--rule 一起使用，自动获取 trade IDs。",
    )
    backfill_days_parser.add_argument(
        "--fund",
        type=str,
        default=None,
        help="基金代码（与 --batch-id 一起使用）",
    )
    backfill_days_parser.add_argument(
        "--freq",
        choices=["daily", "weekly", "monthly"],
        default=None,
        help="定投频率（与 --batch-id 一起使用）",
    )
    backfill_days_parser.add_argument(
        "--rule",
        type=str,
        default=None,
        help="定投规则（与 --batch-id 一起使用）",
    )
    backfill_days_parser.add_argument(
        "--valid-amounts",
        type=str,
        required=True,
        help="有效金额列表（逗号分隔，如 100,20,10）。AI 从 Facts 推断后指定。",
    )

    # ========== set-core 子命令（v0.4.5 AI 驱动）==========
    set_core_parser = subparsers.add_parser(
        "set-core", help="设置某笔交易为当天的 DCA 核心（AI 驱动）"
    )
    set_core_parser.add_argument("--trade-id", type=int, required=True, help="交易 ID")
    set_core_parser.add_argument(
        "--plan-key",
        type=str,
        required=True,
        help="DCA 计划标识（通常为 fund_code）",
    )

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


def _do_backfill_days(args: argparse.Namespace) -> int:
    """执行 backfill-days 命令：批量回填指定交易为 DCA 核心。"""
    try:
        # 1. 解析有效金额（必填）
        valid_amounts_str = args.valid_amounts
        valid_amounts = [Decimal(x.strip()) for x in valid_amounts_str.split(",")]
        log(f"[DCA:backfill-days] 有效金额: {valid_amounts}")

        # 2. 获取 trade IDs（两种方式二选一）
        trade_ids: list[int] = []
        plan_key: str = ""

        if args.trade_ids:
            # 方式1：直接指定 trade IDs
            trade_ids = [int(x.strip()) for x in args.trade_ids.split(",")]
            # 需要从第一笔交易推断 plan_key（或者要求用户提供）
            # 简化处理：要求同时提供 --fund
            if not args.fund:
                log("❌ 使用 --trade-ids 时必须同时提供 --fund")
                return 1
            plan_key = args.fund
            log(f"[DCA:backfill-days] 直接指定 {len(trade_ids)} 笔交易")

        elif args.batch_id and args.fund and args.freq is not None:
            # 方式2：自动获取（推荐）
            batch_id = args.batch_id
            fund_code = args.fund
            freq = args.freq
            rule = args.rule or ""
            plan_key = fund_code

            log(f"[DCA:backfill-days] 自动获取 trade IDs: batch={batch_id}, fund={fund_code}, {freq}/{rule}")

            # 调用 checks 获取符合条件的 trade IDs
            day_checks = checks(
                batch_id=batch_id,
                code=fund_code,
                freq=freq,
                rule=rule,
                valid_amounts=valid_amounts,
            )

            # 只选择：在轨道上 + 一天一笔的交易
            for check in day_checks:
                if check.on_track and check.count == 1:
                    trade_ids.append(check.ids[0])

            log(f"[DCA:backfill-days] 自动获取 {len(trade_ids)} 笔符合条件的交易")

        else:
            log("❌ 必须提供 --trade-ids 或 --batch-id + --fund + --freq")
            return 1

        if not trade_ids:
            log("（无可回填交易）")
            return 0

        # 3. 调用 Flow
        result = backfill(
            trade_ids=trade_ids,
            plan_key=plan_key,
            valid_amounts=valid_amounts,
        )

        # 4. 输出结果
        log(f"\n📊 回填结果：输入 {result.total} 笔 → 更新 {result.updated} 笔")

        if result.skipped:
            log(f"\n⚠️ 跳过 {len(result.skipped)} 笔（供 AI 审核）：")
            for st in result.skipped:
                log(f"   • ID={st.id} | {st.code} | {st.day} | {st.amount}元")
                log(f"     原因: {st.reason}")

        if result.updated > 0:
            log(f"\n✅ 已更新 {result.updated} 笔交易")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 批量回填失败：{err}")
        return 5


def _do_set_core(args: argparse.Namespace) -> int:
    """执行 set-core 命令：设置某笔交易为当天的 DCA 核心。"""
    try:
        # 1. 解析参数
        trade_id = args.trade_id
        plan_key = args.plan_key

        log(f"[DCA:set-core] 设置交易 {trade_id} 为 DCA 核心，plan_key={plan_key}")

        # 2. 调用 Flow
        success = set_core(trade_id=trade_id, plan_key=plan_key)

        # 3. 输出结果
        if success:
            log(f"✅ 交易 {trade_id} 已设为当天 DCA 核心")
            return 0
        else:
            log("❌ 设置失败（交易不存在）")
            return 4
    except Exception as err:  # noqa: BLE001
        log(f"❌ 设置 DCA 核心失败：{err}")
        return 5


def main() -> int:
    """
    定投计划管理 CLI（v0.4.5）。

    Returns:
        退出码：0=成功；4=计划/交易不存在；5=其他失败。
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
    # v0.4.5 AI 驱动的回填命令
    elif args.command == "backfill-days":
        return _do_backfill_days(args)
    elif args.command == "set-core":
        return _do_set_core(args)
    else:
        log(f"❌ 未知命令：{args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
