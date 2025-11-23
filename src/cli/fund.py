from __future__ import annotations

import argparse
import sys

from src.core.log import log
from src.core.models.asset_class import AssetClass
from src.flows.config import add_fund, list_funds


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli.fund",
        description="基金配置管理（v0.3.2）",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="子命令")

    # ========== add 子命令 ==========
    add_parser = subparsers.add_parser("add", help="添加或更新基金")
    add_parser.add_argument("--code", required=True, help="基金代码（6位数字）")
    add_parser.add_argument("--name", required=True, help="基金名称")
    add_parser.add_argument(
        "--class",
        dest="asset_class",
        required=True,
        choices=["CSI300", "US_QDII", "CGB_3_5Y"],
        help="资产类别",
    )
    add_parser.add_argument(
        "--market",
        required=True,
        choices=["CN_A", "US_NYSE"],
        help="市场类型",
    )

    # ========== list 子命令 ==========
    subparsers.add_parser("list", help="列出所有基金")

    return parser.parse_args()


def _do_add(args: argparse.Namespace) -> int:
    """执行 add 命令。"""
    try:
        fund_code = args.code
        name = args.name
        asset_class = AssetClass(args.asset_class)
        market = args.market

        log(f"[Fund:add] 添加基金：{fund_code} - {name} ({asset_class.value}/{market})")
        add_fund(
            fund_code=fund_code,
            name=name,
            asset_class=asset_class,
            market=market,
        )
        log(f"✅ 基金 {fund_code} 添加成功")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 添加基金失败：{err}")
        return 5


def _do_list(_args: argparse.Namespace) -> int:
    """执行 list 命令。"""
    try:
        log("[Fund:list] 查询所有基金")
        funds = list_funds()

        if not funds:
            log("（无基金配置）")
            return 0

        log(f"共 {len(funds)} 个基金：")
        for fund in funds:
            log(f"  {fund.fund_code} | {fund.name} | {fund.asset_class.value} | {fund.market}")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 查询基金失败：{err}")
        return 5


def main() -> int:
    """
    基金配置管理 CLI（v0.3.2）。

    Returns:
        退出码：0=成功；5=失败。
    """
    args = _parse_args()

    if args.command == "add":
        return _do_add(args)
    elif args.command == "list":
        return _do_list(args)
    else:
        log(f"❌ 未知命令：{args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
