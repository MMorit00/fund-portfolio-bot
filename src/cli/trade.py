from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal

from src.core.log import log
from src.flows.trade import create_trade, list_trades


def _parse_args() -> argparse.Namespace:
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

    # ========== sell 子命令 ==========
    sell_parser = subparsers.add_parser("sell", help="创建卖出交易")
    sell_parser.add_argument("--fund", required=True, help="基金代码")
    sell_parser.add_argument("--amount", required=True, type=Decimal, help="卖出金额")
    sell_parser.add_argument(
        "--date",
        help="交易日期（YYYY-MM-DD，默认今天）",
    )

    # ========== list 子命令 ==========
    list_parser = subparsers.add_parser("list", help="查询交易记录")
    list_parser.add_argument(
        "--status",
        choices=["pending", "confirmed", "skipped"],
        help="按状态过滤（不指定则显示全部）",
    )

    return parser.parse_args()


def _do_buy(args: argparse.Namespace) -> int:
    """执行 buy 命令。"""
    try:
        fund_code = args.fund
        amount = args.amount
        trade_day = date.fromisoformat(args.date) if args.date else date.today()

        log(f"[Trade:buy] 创建买入交易：{fund_code} - {amount} 元 @ {trade_day}")
        trade = create_trade(
            fund_code=fund_code,
            trade_type="buy",
            amount=amount,
            trade_day=trade_day,
        )
        log(
            f"✅ 交易创建成功：ID={trade.id}，定价日={trade.pricing_date}，确认日={trade.confirm_date}"
        )
        return 0
    except ValueError as err:
        log(f"❌ 创建失败：{err}")
        return 4
    except Exception as err:  # noqa: BLE001
        log(f"❌ 创建买入交易失败：{err}")
        return 5


def _do_sell(args: argparse.Namespace) -> int:
    """执行 sell 命令。"""
    try:
        fund_code = args.fund
        amount = args.amount
        trade_day = date.fromisoformat(args.date) if args.date else date.today()

        log(f"[Trade:sell] 创建卖出交易：{fund_code} - {amount} 元 @ {trade_day}")
        trade = create_trade(
            fund_code=fund_code,
            trade_type="sell",
            amount=amount,
            trade_day=trade_day,
        )
        log(
            f"✅ 交易创建成功：ID={trade.id}，定价日={trade.pricing_date}，确认日={trade.confirm_date}"
        )
        return 0
    except ValueError as err:
        log(f"❌ 创建失败：{err}")
        return 4
    except Exception as err:  # noqa: BLE001
        log(f"❌ 创建卖出交易失败：{err}")
        return 5


def _do_list(args: argparse.Namespace) -> int:
    """执行 list 命令。"""
    try:
        status = args.status
        log(f"[Trade:list] 查询交易记录（status={status or '全部'}）")
        trades = list_trades(status=status)

        if not trades:
            log("（无交易记录）")
            return 0

        log(f"共 {len(trades)} 笔交易：")
        for trade in trades:
            # 构造状态图标
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

            # 构造交易信息
            type_str = "买入" if trade.type == "buy" else "卖出"
            shares_str = f"{trade.shares} 份" if trade.shares else "待确认"

            log(
                f"  {status_icon} [{trade.id}] {trade.fund_code} | {type_str} {trade.amount} 元 | "
                f"{shares_str} | {trade.trade_date} → {trade.confirm_date} | {trade.status}"
            )

            # 延迟提示
            if trade.confirmation_status == "delayed":
                log(f"       ⚠️  延迟原因：{trade.delayed_reason}，自 {trade.delayed_since}")

        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 查询交易失败：{err}")
        return 5


def main() -> int:
    """
    手动交易管理 CLI（v0.3.2）。

    Returns:
        退出码：0=成功；4=参数错误；5=其他失败。
    """
    args = _parse_args()

    if args.command == "buy":
        return _do_buy(args)
    elif args.command == "sell":
        return _do_sell(args)
    elif args.command == "list":
        return _do_list(args)
    else:
        log(f"❌ 未知命令：{args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
