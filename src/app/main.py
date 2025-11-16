from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal, InvalidOperation

from src.app.log import log
from src.app.wiring import DependencyContainer
from src.core.trading.settlement import get_confirm_date


def parse_args() -> argparse.Namespace:
    """
    解析命令行参数。

    子命令：buy / sell / skip-dca / status
    - buy/sell 公共参数：--fund-code（必需）、--amount（必需）、--date（可选，ISO 格式）
    - skip-dca 参数：--fund-code（必需）、--date（可选，默认今天）
    - status 参数：无（输出当前市值视图）

    Returns:
        解析后的参数命名空间。
    """
    parser = argparse.ArgumentParser(
        prog="python -m src.app.main",
        description="基金投资组合管理 CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # buy 子命令
    buy_parser = subparsers.add_parser("buy", help="买入基金")
    buy_parser.add_argument("--fund-code", required=True, help="基金代码")
    buy_parser.add_argument("--amount", required=True, help="买入金额（例如 1000 或 1000.50）")
    buy_parser.add_argument("--date", help="交易日期（格式：YYYY-MM-DD，默认今天）")

    # sell 子命令
    sell_parser = subparsers.add_parser("sell", help="卖出基金")
    sell_parser.add_argument("--fund-code", required=True, help="基金代码")
    sell_parser.add_argument("--amount", required=True, help="卖出金额（例如 500 或 500.50）")
    sell_parser.add_argument("--date", help="交易日期（格式：YYYY-MM-DD，默认今天）")

    # skip-dca 子命令
    skip_parser = subparsers.add_parser("skip-dca", help="跳过指定日期的定投")
    skip_parser.add_argument("--fund-code", required=True, help="基金代码")
    skip_parser.add_argument("--date", help="目标日期（格式：YYYY-MM-DD，默认今天）")

    status_parser = subparsers.add_parser("status", help="打印当前持仓市值与偏离")
    status_parser.add_argument(
        "--show-rebalance",
        action="store_true",
        help="附加输出再平衡建议（基础版，仅文字提示）",
    )

    return parser.parse_args()


def parse_date(date_str: str | None) -> date:
    """
    解析日期参数。

    Args:
        date_str: ISO 日期字符串或 None。

    Returns:
        解析后的日期；None 时返回今天。

    Raises:
        ValueError: 非法日期格式。
    """
    if not date_str:
        return date.today()

    try:
        return date.fromisoformat(date_str)
    except ValueError as e:
        raise ValueError(f"日期格式无效：{date_str}（期望格式：YYYY-MM-DD，例如 2025-11-15）") from e


def parse_amount(amount_str: str) -> Decimal:
    """
    解析金额参数。

    Args:
        amount_str: 金额字符串。

    Returns:
        Decimal 金额，要求 > 0。

    Raises:
        ValueError: 非法金额或非正数。
    """
    try:
        amount = Decimal(amount_str)
        if amount <= Decimal("0"):
            raise ValueError("金额必须大于 0")
        return amount
    except InvalidOperation as e:
        raise ValueError(f"金额格式无效：{amount_str}（期望 Decimal，例如 1000 或 1000.50）") from e


def main() -> int:
    """
    CLI 入口：处理 buy / sell / skip-dca / status 命令。

    Returns:
        退出码：0=成功；4=参数/业务错误；5=未知错误。
    """
    args = parse_args()

    if not args.command:
        log("请指定命令：buy / sell / skip-dca / status")
        log("使用 --help 查看帮助")
        return 4

    try:
        if args.command in {"buy", "sell"}:
            fund_code = args.fund_code
            amount = parse_amount(args.amount)
            trade_day = parse_date(args.date)
            trade_type = args.command

            with DependencyContainer() as container:
                usecase = container.get_create_trade_usecase()
                trade = usecase.execute(
                    fund_code=fund_code,
                    trade_type=trade_type,
                    amount=amount,
                    trade_day=trade_day,
                )
                # 计算确认日（基于 v0.2 日历与规则）
                confirm_date = get_confirm_date(trade.market, trade.trade_date, container.calendar)

            log(
                f"✅ 交易已创建：ID={trade.id} fund={trade.fund_code} type={trade.type} "
                f"amount={trade.amount} date={trade.trade_date} confirm_date={confirm_date}"
            )
            return 0

        if args.command == "skip-dca":
            fund_code = args.fund_code
            target_day = parse_date(args.date)

            with DependencyContainer() as container:
                usecase = container.get_skip_dca_usecase()
                affected = usecase.execute(fund_code=fund_code, day=target_day)

            log(f"✅ 已跳过 {target_day} 的定投：fund={fund_code}，影响 {affected} 条 pending 记录")
            return 0

        if args.command == "status":
            with DependencyContainer() as container:
                report_uc = container.get_daily_report_usecase()
                text = report_uc.build(mode="market")
                if getattr(args, "show_rebalance", False):
                    from datetime import date as _date
                    from src.core.portfolio.rebalance import RebalanceAdvice

                    rebalance_uc = container.get_rebalance_suggestion_usecase()
                    result = rebalance_uc.execute(today=_date.today())

                    lines: list[str] = [text.rstrip(), "\n再平衡建议（基础版）：\n"]
                    if getattr(result, "no_market_data", False):
                        # 当日 NAV 缺失，无法给出金额建议
                        lines.append("- 当日 NAV 缺失，无法给出金额建议\n")
                        text = "".join(lines)
                        log(text)
                        return 0

                    any_action = False
                    for adv in result.suggestions:
                        if adv.action == "hold":
                            continue
                        any_action = True
                        dev_pct = adv.weight_diff * 100
                        th_pct = adv.threshold * 100
                        amount = adv.amount.quantize(Decimal("0.01"))
                        direction = "增持" if adv.action == "buy" else "减持"
                        lines.append(
                            f"- {adv.asset_class.value}：偏离 {dev_pct:.1f}%（阈值 {th_pct:.1f}%），建议{direction} {amount} 元\n"
                        )
                    if not any_action:
                        lines.append("- 所有资产类别均在阈值内，观察\n")
                    text = "".join(lines)
            log(text)
            return 0

        log(f"未知命令：{args.command}")
        return 4

    except ValueError as err:
        log(f"❌ 错误：{err}")
        if "未知基金代码" in str(err):
            log("提示：请检查是否已在 funds 表中配置，或先运行 dev_seed_db")
        return 4

    except Exception as err:  # noqa: BLE001
        log(f"❌ 未知错误：{err}")
        return 5


if __name__ == "__main__":
    sys.exit(main())
