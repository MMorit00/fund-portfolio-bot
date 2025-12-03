from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal

from src.core.log import log
from src.core.models.trade import Trade
from src.flows.trade import cancel_trade, confirm_trade_manual, create_trade, list_trades


def _parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        prog="python -m src.cli.trade",
        description="手动交易管理（v0.3.2）",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="子命令")

    # ========== buy 子命令 ==========
    buy_parser = subparsers.add_parser("buy", help="创建买入交易")
    buy_parser.add_argument("--fund", required=True, help="基金代码")
    buy_parser.add_argument("--amount", required=True, type=Decimal, help="买入金额")
    buy_parser.add_argument(
        "--date",
        help="交易日期（YYYY-MM-DD，默认今天）",
    )
    buy_parser.add_argument(
        "--intent",
        choices=["planned", "impulse", "opportunistic", "exit", "rebalance"],
        help="意图标签",
    )
    buy_parser.add_argument("--note", help="备注")

    # ========== sell 子命令 ==========
    sell_parser = subparsers.add_parser("sell", help="创建卖出交易")
    sell_parser.add_argument("--fund", required=True, help="基金代码")
    sell_parser.add_argument("--amount", required=True, type=Decimal, help="卖出金额")
    sell_parser.add_argument(
        "--date",
        help="交易日期（YYYY-MM-DD，默认今天）",
    )
    sell_parser.add_argument(
        "--intent",
        choices=["planned", "impulse", "opportunistic", "exit", "rebalance"],
        help="意图标签",
    )
    sell_parser.add_argument("--note", help="备注")

    # ========== list 子命令 ==========
    list_parser = subparsers.add_parser("list", help="查询交易记录")
    list_parser.add_argument(
        "--status",
        choices=["pending", "confirmed", "skipped"],
        help="按状态过滤（不指定则显示全部）",
    )

    # ========== cancel 子命令 ==========
    cancel_parser = subparsers.add_parser("cancel", help="取消 pending 交易")
    cancel_parser.add_argument("--id", required=True, type=int, help="交易 ID")
    cancel_parser.add_argument("--note", help="取消原因")

    # ========== confirm-manual 子命令 ==========
    confirm_manual_parser = subparsers.add_parser(
        "confirm-manual",
        help="手动确认 pending 交易（应对 NAV 永久缺失场景）",
    )
    confirm_manual_parser.add_argument("--id", required=True, type=int, help="交易 ID")
    confirm_manual_parser.add_argument(
        "--shares",
        required=True,
        type=Decimal,
        help="确认份额（从支付宝等平台复制）",
    )
    confirm_manual_parser.add_argument(
        "--nav",
        required=True,
        type=Decimal,
        help="确认净值（从支付宝等平台复制）",
    )

    return parser.parse_args()


def _format_trade_created(trade_id: int, pricing_date: date, confirm_date: date) -> None:
    """格式化交易创建成功输出。

    Args:
        trade_id: 交易 ID。
        pricing_date: 定价日。
        confirm_date: 确认日。
    """
    log(f"✅ 交易创建成功：ID={trade_id}，定价日={pricing_date}，确认日={confirm_date}")


def _format_trade(trade: Trade) -> None:
    """格式化单笔交易输出。

    Args:
        trade: 交易对象。
    """
    # 1. 构造状态图标
    if trade.status == "pending":
        if trade.confirmation_status == "delayed":
            status_icon = "⚠️ "
        else:
            status_icon = "⏳"
    elif trade.status == "confirmed":
        status_icon = "✅"
    elif trade.status == "skipped":
        status_icon = "⏭️ "
    else:
        status_icon = "  "

    # 2. 构造交易信息
    type_str = "买入" if trade.type == "buy" else "卖出"
    shares_str = f"{trade.shares} 份" if trade.shares else "待确认"

    # 3. 输出主要信息
    log(
        f"  {status_icon} [{trade.id}] {trade.fund_code} | {type_str} {trade.amount} 元 | "
        f"{shares_str} | {trade.trade_date} → {trade.confirm_date} | {trade.status}"
    )

    # 4. 延迟提示
    if trade.confirmation_status == "delayed":
        log(f"       ⚠️  延迟原因：{trade.delayed_reason}，自 {trade.delayed_since}")


def _do_buy(args: argparse.Namespace) -> int:
    """执行 buy 命令。

    Args:
        args: 命令行参数。

    Returns:
        退出码：0=成功；4=参数错误；5=其他失败。
    """
    try:
        # 1. 解析参数
        fund_code = args.fund
        amount = args.amount
        trade_day = date.fromisoformat(args.date) if args.date else date.today()
        intent = args.intent
        note = args.note

        # 2. 输出操作提示
        log(f"[Trade:buy] 创建买入交易：{fund_code} - {amount} 元 @ {trade_day}")

        # 3. 调用 Flow 函数
        trade = create_trade(
            fund_code=fund_code,
            trade_type="buy",
            amount=amount,
            trade_day=trade_day,
            intent=intent,
            note=note,
        )

        # 4. 格式化输出
        _format_trade_created(trade.id, trade.pricing_date, trade.confirm_date)

        return 0
    except ValueError as err:
        log(f"❌ 创建失败：{err}")
        return 4
    except Exception as err:  # noqa: BLE001
        log(f"❌ 创建买入交易失败：{err}")
        return 5


def _do_sell(args: argparse.Namespace) -> int:
    """执行 sell 命令。

    Args:
        args: 命令行参数。

    Returns:
        退出码：0=成功；4=参数错误；5=其他失败。
    """
    try:
        # 1. 解析参数
        fund_code = args.fund
        amount = args.amount
        trade_day = date.fromisoformat(args.date) if args.date else date.today()
        intent = args.intent
        note = args.note

        # 2. 输出操作提示
        log(f"[Trade:sell] 创建卖出交易：{fund_code} - {amount} 元 @ {trade_day}")

        # 3. 调用 Flow 函数
        trade = create_trade(
            fund_code=fund_code,
            trade_type="sell",
            amount=amount,
            trade_day=trade_day,
            intent=intent,
            note=note,
        )

        # 4. 格式化输出
        _format_trade_created(trade.id, trade.pricing_date, trade.confirm_date)

        return 0
    except ValueError as err:
        log(f"❌ 创建失败：{err}")
        return 4
    except Exception as err:  # noqa: BLE001
        log(f"❌ 创建卖出交易失败：{err}")
        return 5


def _do_cancel(args: argparse.Namespace) -> int:
    """执行 cancel 命令。

    Args:
        args: 命令行参数。

    Returns:
        退出码：0=成功；4=参数错误；5=其他失败。
    """
    try:
        # 1. 解析参数
        trade_id = args.id
        note = args.note

        # 2. 输出操作提示
        log(f"[Trade:cancel] 取消交易：ID={trade_id}")

        # 3. 调用 Flow 函数
        cancel_trade(trade_id=trade_id, note=note)

        # 4. 输出结果
        log(f"✅ 交易 {trade_id} 已取消")

        return 0
    except ValueError as err:
        log(f"❌ 取消失败：{err}")
        return 4
    except Exception as err:  # noqa: BLE001
        log(f"❌ 取消交易失败：{err}")
        return 5


def _do_confirm_manual(args: argparse.Namespace) -> int:
    """执行 confirm-manual 命令。

    Args:
        args: 命令行参数。

    Returns:
        退出码：0=成功；4=参数错误；5=其他失败。
    """
    try:
        # 1. 解析参数
        trade_id = args.id
        shares = args.shares
        nav = args.nav

        # 2. 输出操作提示
        log(f"[Trade:confirm-manual] 手动确认交易：ID={trade_id}，份额={shares}，NAV={nav}")

        # 3. 调用 Flow 函数
        confirm_trade_manual(trade_id=trade_id, shares=shares, nav=nav)

        # 4. 输出结果
        log(f"✅ 交易 {trade_id} 已手动确认（份额={shares}，NAV={nav}）")

        return 0
    except ValueError as err:
        log(f"❌ 手动确认失败：{err}")
        return 4
    except Exception as err:  # noqa: BLE001
        log(f"❌ 手动确认交易失败：{err}")
        return 5


def _do_list(args: argparse.Namespace) -> int:
    """执行 list 命令。

    Args:
        args: 命令行参数。

    Returns:
        退出码：0=成功；5=其他失败。
    """
    try:
        # 1. 解析参数
        status = args.status

        # 2. 输出操作提示
        log(f"[Trade:list] 查询交易记录（status={status or '全部'}）")

        # 3. 调用 Flow 函数
        trades = list_trades(status=status)

        # 4. 格式化输出
        if not trades:
            log("（无交易记录）")
            return 0

        log(f"共 {len(trades)} 笔交易：")
        for trade in trades:
            _format_trade(trade)

        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 查询交易失败：{err}")
        return 5


def main() -> int:
    """
    手动交易管理 CLI（v0.3.4+）。

    Returns:
        退出码：0=成功；4=参数错误；5=其他失败。
    """
    # 1. 解析参数
    args = _parse_args()

    # 2. 分发命令
    if args.command == "buy":
        return _do_buy(args)
    elif args.command == "sell":
        return _do_sell(args)
    elif args.command == "list":
        return _do_list(args)
    elif args.command == "cancel":
        return _do_cancel(args)
    elif args.command == "confirm-manual":
        return _do_confirm_manual(args)
    else:
        log(f"❌ 未知命令：{args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
