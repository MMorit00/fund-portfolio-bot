from __future__ import annotations

import argparse
import sys

from src.core.container import get_fund_repo
from src.core.log import log
from src.core.models.asset_class import AssetClass
from src.flows.config import add_fund, list_funds, remove_fund
from src.flows.fund_fees import get_fund_fees, sync_fund_fees


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli.fund",
        description="基金配置管理（v0.4.3）",
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
    add_parser.add_argument(
        "--alias",
        required=False,
        help="平台完整基金名称（可选，用于导入时匹配）",
    )

    # ========== list 子命令 ==========
    subparsers.add_parser("list", help="列出所有基金")

    # ========== remove 子命令 ==========
    remove_parser = subparsers.add_parser("remove", help="删除基金")
    remove_parser.add_argument("--code", required=True, help="基金代码（6位数字）")

    # ========== fees 子命令 ==========
    fees_parser = subparsers.add_parser("fees", help="查看基金费率")
    fees_parser.add_argument("--code", required=True, help="基金代码（6位数字）")

    # ========== sync-fees 子命令 ==========
    sync_fees_parser = subparsers.add_parser("sync-fees", help="同步基金费率（从东方财富抓取）")
    sync_fees_parser.add_argument("--code", help="基金代码（不指定则同步全部）")

    return parser.parse_args()


def _do_add(args: argparse.Namespace) -> int:
    """执行 add 命令。"""
    try:
        fund_code = args.code
        name = args.name
        asset_class = AssetClass(args.asset_class)
        market = args.market
        alias = args.alias if hasattr(args, "alias") else None

        log(f"[Fund:add] 添加基金：{fund_code} - {name} ({asset_class.value}/{market})")
        add_fund(
            fund_code=fund_code,
            name=name,
            asset_class=asset_class,
            market=market,
            alias=alias,
        )
        log(f"✅ 基金 {fund_code} 添加成功")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 添加基金失败：{err}")
        return 5


def _do_remove(args: argparse.Namespace) -> int:
    """执行 remove 命令。"""
    try:
        fund_code = args.code
        log(f"[Fund:remove] 删除基金：{fund_code}")
        remove_fund(fund_code=fund_code)
        log(f"✅ 基金 {fund_code} 删除成功")
        return 0
    except ValueError as err:
        log(f"❌ 删除失败：{err}")
        return 4
    except Exception as err:  # noqa: BLE001
        log(f"❌ 删除基金失败：{err}")
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


def _do_fees(args: argparse.Namespace) -> int:
    """执行 fees 命令：查看基金费率。"""
    try:
        # 获取基金信息
        fund_repo = get_fund_repo()
        fund_info = fund_repo.get(args.code)
        if fund_info is None:
            log(f"❌ 基金不存在：{args.code}")
            return 4

        # 获取费率信息
        fees = get_fund_fees(args.code)

        print(f"\n📊 {fund_info.name} ({fund_info.fund_code}) 费率信息\n")

        if fees is None:
            print("⚠️  费率信息未同步，请运行 sync-fees 命令")
            print()
            return 0

        # 运作费用（注意：Decimal("0") 是 falsy，需要用 is not None 判断）
        print("运作费用（年化，从净值中扣除）：")
        print(f"  管理费率: {fees.management_fee}%" if fees.management_fee is not None else "  管理费率: 未知")
        print(f"  托管费率: {fees.custody_fee}%" if fees.custody_fee is not None else "  托管费率: 未知")
        print(f"  销售服务费率: {fees.service_fee}%" if fees.service_fee is not None else "  销售服务费率: 未知")

        # 申购费用
        print("\n申购费用：")
        if fees.purchase_fee is not None:
            print(f"  申购费率（原）: {fees.purchase_fee}%")
        if fees.purchase_fee_discount is not None:
            print(f"  申购费率（折扣）: {fees.purchase_fee_discount}%")
        if fees.purchase_fee is None and fees.purchase_fee_discount is None:
            print("  未知")

        # 赎回费用（阶梯）
        print("\n赎回费用（按持有天数）：")
        if fees.redemption_tiers:
            for tier in fees.redemption_tiers:
                if tier.max_hold_days is None:
                    print(f"  持有 ≥{tier.min_hold_days} 天: {tier.rate}%")
                else:
                    print(f"  持有 {tier.min_hold_days}-{tier.max_hold_days} 天: {tier.rate}%")
        else:
            print("  未知")

        # 检查费率是否完整
        has_operating_fees = fees.management_fee is not None or fees.custody_fee is not None
        has_trading_fees = fees.purchase_fee is not None or fees.redemption_tiers
        if not has_operating_fees or not has_trading_fees:
            print("\n⚠️  费率信息不完整，建议运行 sync-fees 命令补全")

        print()
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 查询费率失败：{err}")
        return 5


def _do_sync_fees(args: argparse.Namespace) -> int:
    """执行 sync-fees 命令：同步基金费率。"""
    try:
        result = sync_fund_fees(args.code)

        if not result.details:
            log("（无基金配置）")
            return 0

        if args.code:
            # 单只基金
            _, name, success = result.details[0]
            if success:
                log(f"✅ {args.code} {name} 费率同步成功")
            else:
                log(f"❌ {args.code} {name} 费率同步失败")
                return 5
        else:
            # 全部基金
            log(f"同步 {len(result.details)} 个基金费率...")
            for fund_code, name, success in result.details:
                if success:
                    log(f"  ✅ {fund_code} {name}")
                else:
                    log(f"  ❌ {fund_code} {name}")
            log(f"\n同步完成：成功 {result.success}，失败 {result.failed}")

        return 0
    except ValueError as err:
        log(f"❌ {err}")
        return 4
    except Exception as err:  # noqa: BLE001
        log(f"❌ 同步费率失败：{err}")
        return 5


def main() -> int:
    """
    基金配置管理 CLI（v0.4.3）。

    Returns:
        退出码：0=成功；4=参数错误；5=其他失败。
    """
    args = _parse_args()

    if args.command == "add":
        return _do_add(args)
    elif args.command == "list":
        return _do_list(args)
    elif args.command == "remove":
        return _do_remove(args)
    elif args.command == "fees":
        return _do_fees(args)
    elif args.command == "sync-fees":
        return _do_sync_fees(args)
    else:
        log(f"❌ 未知命令：{args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
