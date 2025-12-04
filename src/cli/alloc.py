from __future__ import annotations

import argparse
import sys
from decimal import Decimal

from src.core.log import log
from src.core.models import AssetClass
from src.flows.config import delete_allocation, list_allocations, set_allocation


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli.alloc",
        description="资产配置目标管理（v0.3.2）",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="子命令")

    # ========== set 子命令 ==========
    set_parser = subparsers.add_parser("set", help="设置资产配置目标")
    set_parser.add_argument(
        "--class",
        dest="asset_class",
        required=True,
        choices=["CSI300", "US_QDII", "CGB_3_5Y"],
        help="资产类别",
    )
    set_parser.add_argument(
        "--target",
        required=True,
        type=Decimal,
        help="目标权重（0..1，如 0.6）",
    )
    set_parser.add_argument(
        "--deviation",
        required=True,
        type=Decimal,
        help="允许的最大偏离（0..1，如 0.05）",
    )

    # ========== show 子命令 ==========
    subparsers.add_parser("show", help="查看所有资产配置目标")

    # ========== delete 子命令 ==========
    delete_parser = subparsers.add_parser("delete", help="删除资产配置目标")
    delete_parser.add_argument(
        "--class",
        dest="asset_class",
        required=True,
        choices=["CSI300", "US_QDII", "CGB_3_5Y"],
        help="资产类别",
    )

    return parser.parse_args()


def _do_set(args: argparse.Namespace) -> int:
    """执行 set 命令。"""
    try:
        # 1. 解析参数
        asset_class = AssetClass(args.asset_class)
        target_weight = args.target
        max_deviation = args.deviation

        # 2. 验证参数范围
        if not (Decimal("0") <= target_weight <= Decimal("1")):
            log("❌ 目标权重必须在 0..1 范围内")
            return 4
        if not (Decimal("0") <= max_deviation <= Decimal("1")):
            log("❌ 最大偏离必须在 0..1 范围内")
            return 4

        # 3. 设置资产配置
        log(
            f"[Alloc:set] 设置配置：{asset_class} - 目标 {target_weight*100:.1f}%，偏离 ±{max_deviation*100:.1f}%"
        )
        set_allocation(
            asset_class=asset_class,
            target_weight=target_weight,
            max_deviation=max_deviation,
        )
        log(f"✅ 资产配置 {asset_class.value} 设置成功")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 设置资产配置失败：{err}")
        return 5


def _do_delete(args: argparse.Namespace) -> int:
    """执行 delete 命令。"""
    try:
        # 1. 解析参数
        asset_class = AssetClass(args.asset_class)

        # 2. 删除资产配置
        log(f"[Alloc:delete] 删除资产配置：{asset_class.value}")
        delete_allocation(asset_class=asset_class)
        log(f"✅ 资产配置 {asset_class.value} 删除成功")
        return 0
    except ValueError as err:
        log(f"❌ 删除失败：{err}")
        return 4
    except Exception as err:  # noqa: BLE001
        log(f"❌ 删除资产配置失败：{err}")
        return 5


def _do_show(_args: argparse.Namespace) -> int:
    """执行 show 命令。"""
    try:
        # 1. 查询所有资产配置
        log("[Alloc:show] 查询所有资产配置目标")
        configs = list_allocations()

        if not configs:
            log("（无资产配置）")
            return 0

        # 2. 格式化输出
        log(f"共 {len(configs)} 个资产配置：")
        total_weight = Decimal("0")
        for config in configs:
            log(
                f"  {config.asset_class.value} | 目标 {config.target_weight*100:.1f}% | 偏离 ±{config.max_deviation*100:.1f}%"
            )
            total_weight += config.target_weight

        # 3. 验证总权重
        if total_weight != Decimal("1"):
            log(f"⚠️  注意：总权重 = {total_weight*100:.1f}%（期望 100%）")
        else:
            log(f"✅ 总权重 = {total_weight*100:.0f}%")

        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 查询资产配置失败：{err}")
        return 5


def main() -> int:
    """
    资产配置目标管理 CLI（v0.3.4）。

    Returns:
        退出码：0=成功；4=参数错误；5=其他失败。
    """
    # 1. 解析参数
    args = _parse_args()

    # 2. 路由到子命令
    if args.command == "set":
        return _do_set(args)
    elif args.command == "show":
        return _do_show(args)
    elif args.command == "delete":
        return _do_delete(args)
    else:
        log(f"❌ 未知命令：{args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
