"""基金限购/暂停公告管理 CLI（v0.4.4）。"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal

from src.core.log import log
from src.core.models.fund_restriction import ParsedRestriction
from src.flows.fund_restriction import (
    RestrictionResult,
    add_restriction,
    end_restriction,
    fetch_restriction,
    save_restriction,
)


def _parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        prog="uv run python -m src.cli.fund_restriction",
        description="基金限购/暂停公告管理（v0.4.4）",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="子命令")

    # ========== add 子命令 ==========
    add_parser = subparsers.add_parser("add", help="手动录入限制记录")
    add_parser.add_argument("--fund", required=True, help="基金代码")
    add_parser.add_argument(
        "--type",
        required=True,
        choices=["daily_limit", "suspend", "resume"],
        help="限制类型",
    )
    add_parser.add_argument(
        "--start",
        required=True,
        help="开始日期（YYYY-MM-DD）",
    )
    add_parser.add_argument(
        "--end",
        default=None,
        help="结束日期（YYYY-MM-DD），不提供表示仍在限制中",
    )
    add_parser.add_argument(
        "--limit",
        type=Decimal,
        default=None,
        help="限购金额（仅 daily_limit 时有值，如 10.00）",
    )
    add_parser.add_argument(
        "--note",
        default=None,
        help="备注说明",
    )
    add_parser.add_argument(
        "--source",
        default="manual",
        help="数据来源（默认 manual）",
    )
    add_parser.add_argument(
        "--url",
        default=None,
        help="公告链接（可选）",
    )

    # ========== end 子命令 ==========
    end_parser = subparsers.add_parser("end", help="结束限制记录")
    end_parser.add_argument("--fund", required=True, help="基金代码")
    end_parser.add_argument(
        "--type",
        required=True,
        choices=["daily_limit", "suspend", "resume"],
        help="限制类型",
    )
    end_parser.add_argument(
        "--date",
        required=True,
        help="结束日期（YYYY-MM-DD）",
    )

    # ========== check-status 子命令 ==========
    status_parser = subparsers.add_parser(
        "check-status", help="查询基金当前交易状态（通过 AKShare）"
    )
    status_parser.add_argument("--fund", required=True, help="基金代码")
    status_parser.add_argument(
        "--apply",
        action="store_true",
        help="自动插入到数据库（需确认）",
    )

    return parser.parse_args()


def _format_add_result(result: RestrictionResult) -> None:
    """格式化添加结果输出。"""
    log(f"✅ 限制记录已添加（ID={result.record_id}）")
    log(f"   基金: {result.fund_code}")
    log(f"   类型: {result.restriction_type}")
    log(f"   开始: {result.start_date}")
    log(f"   结束: {result.end_date or '仍在限制中'}")
    if result.limit_amount:
        log(f"   限额: {result.limit_amount} 元")


def _format_end_result(
    success: bool, fund_code: str, restriction_type: str, end_date: date
) -> None:
    """格式化结束结果输出。"""
    if success:
        log(f"✅ 已结束 {fund_code} 的 {restriction_type} 限制（结束日期={end_date}）")
    else:
        log("❌ 未找到符合条件的 active 限制记录")
        log(f"   基金: {fund_code}")
        log(f"   类型: {restriction_type}")
        log(f"   提示: 请使用 'check-status --fund {fund_code}' 查看当前状态")


def _format_check_result(fund_code: str, parsed: ParsedRestriction | None) -> None:
    """格式化查询结果输出。"""
    if not parsed:
        log("（当前无交易限制，申购状态=开放申购）")
        return

    log(f"\n📊 {fund_code} 当前交易状态：")
    log("=" * 80)
    log(f"\n  类型: {parsed.restriction_type}")
    if parsed.limit_amount:
        log(f"  限额: {parsed.limit_amount} 元/日")
    log(f"  置信度: {parsed.confidence}")
    log("  数据源: AKShare fund_purchase_em")
    log(f"  快照日期: {parsed.start_date}")
    log("")
    log("  ⚠️  注意事项：")
    log("     - 上述数据为「当前状态快照」，限额金额准确")
    log("     - 「真实开始日期」未知（可能几个月前就开始限额了）")
    if parsed.note:
        log(f"\n  详细信息: {parsed.note}")


def _do_add(args: argparse.Namespace) -> int:
    """执行 add 命令：手动录入限制记录。"""
    try:
        # 1. 解析参数
        fund_code = args.fund
        restriction_type = args.type
        start_date = date.fromisoformat(args.start)
        end_date = date.fromisoformat(args.end) if args.end else None
        limit_amount = args.limit
        note = args.note
        source = args.source
        source_url = args.url

        # 2. 调用 Flow 函数
        result = add_restriction(
            fund_code=fund_code,
            restriction_type=restriction_type,
            start_date=start_date,
            end_date=end_date,
            limit_amount=limit_amount,
            note=note,
            source=source,
            source_url=source_url,
        )

        # 3. 格式化输出
        _format_add_result(result)

        return 0

    except ValueError as err:
        log(f"❌ 参数错误：{err}")
        return 4
    except Exception as err:  # noqa: BLE001
        log(f"❌ 添加失败：{err}")
        return 5


def _do_end(args: argparse.Namespace) -> int:
    """执行 end 命令：结束限制记录。"""
    try:
        # 1. 解析参数
        fund_code = args.fund
        restriction_type = args.type
        end_date = date.fromisoformat(args.date)

        # 2. 调用 Flow 函数
        success = end_restriction(
            fund_code=fund_code,
            restriction_type=restriction_type,
            end_date=end_date,
        )

        # 3. 格式化输出
        _format_end_result(success, fund_code, restriction_type, end_date)

        return 0 if success else 4

    except ValueError as err:
        log(f"❌ 参数错误：{err}")
        return 4
    except Exception as err:  # noqa: BLE001
        log(f"❌ 结束失败：{err}")
        return 5


def _do_check_status(args: argparse.Namespace) -> int:
    """执行 check-status 命令：查询基金当前交易状态。"""
    try:
        # 1. 解析参数
        fund_code = args.fund
        do_apply = args.apply

        # 2. 调用 Flow 函数
        log(f"[FetchRestriction] 正在查询 {fund_code} 的交易限制（AKShare）...")
        parsed = fetch_restriction(fund_code=fund_code)

        # 3. 格式化输出
        _format_check_result(fund_code, parsed)

        # 4. 如果需要插入，提示用户确认
        if do_apply and parsed:
            log("\n\n❓ 是否将以上状态插入数据库？")
            log("   （请仔细检查解析结果，确认无误后再插入）")
            log("   输入 'yes' 确认，其他任何输入取消：")

            # 读取用户输入
            user_input = input("   > ").strip().lower()

            if user_input == "yes":
                # 调用 save flow
                record_id = save_restriction(
                    fund_code=fund_code,
                    parsed=parsed,
                )

                log(f"\n✅ 已保存：{fund_code} 交易限制（ID={record_id}）")
                return 0
            else:
                log("\n✅ 已取消插入")
                return 0
        elif not parsed:
            # 无限制状态，无需提示
            return 0
        else:
            log("\n\n💡 使用建议：")
            log("   如果以上状态正确，可使用 --apply 标志自动插入：")
            log(
                f"     uv run python -m src.cli.fund_restriction check-status --fund {fund_code} --apply"
            )

        return 0

    except Exception as err:  # noqa: BLE001
        log(f"❌ 查询失败：{err}")
        return 5


def main() -> int:
    """
    基金限购/暂停公告管理 CLI（v0.4.4）。

    用法示例：
        # 查询基金当前交易状态（AKShare）- 主要功能
        uv run python -m src.cli.fund_restriction check-status --fund 016532

        # 添加限购记录（手动录入）
        uv run python -m src.cli.fund_restriction add --fund 008971 --type daily_limit --start 2025-11-01 --limit 10.00 --note "QDII 额度紧张"

        # 结束限制
        uv run python -m src.cli.fund_restriction end --fund 008971 --type daily_limit --date 2025-12-31
    """
    args = _parse_args()

    if args.command == "add":
        return _do_add(args)
    elif args.command == "end":
        return _do_end(args)
    elif args.command == "check-status":
        return _do_check_status(args)
    else:
        log(f"❌ 未知命令: {args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
