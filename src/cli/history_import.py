"""历史账单导入 CLI。

支持从支付宝等平台导入历史基金交易。
详细设计见 docs/history-import.md。

用法：
    # 干跑：检查 CSV 是否有问题
    python -m src.cli.history_import --csv data/alipay.csv --mode dry-run

    # 实际导入
    python -m src.cli.history_import --csv data/alipay.csv --mode apply

    # 禁用 ActionLog 记录
    python -m src.cli.history_import --csv data/alipay.csv --mode apply --no-actions

当前状态：✅ 已实现（实验中），支持支付宝 CSV 导入。
核心功能：CSV 解析、基金外部名称映射、自动创建基金、NAV 抓取、份额计算、去重检查。
NAV 策略：confirmed + NAV 缺失时自动降级为 pending，后续通过 confirm_trades 自动确认。
"""

from __future__ import annotations

import argparse
import sys

from src.core.log import log
from src.core.models import ImportRecord, ImportResult
from src.flows.history_import import import_trades_from_csv


def _parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="从支付宝等平台导入历史基金交易记录",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 干跑模式（只检查，不写入）
  python -m src.cli.history_import --csv data/alipay.csv --mode dry-run

  # 实际导入
  python -m src.cli.history_import --csv data/alipay.csv --mode apply

详细设计见 docs/history-import.md
""",
    )

    parser.add_argument(
        "--csv",
        required=True,
        help="CSV 文件路径（支付宝账单导出）",
    )
    parser.add_argument(
        "--mode",
        choices=["dry-run", "apply"],
        default="dry-run",
        help="导入模式：dry-run=只检查（默认），apply=实际写入",
    )
    parser.add_argument(
        "--source",
        choices=["alipay", "ttjj"],
        default="alipay",
        help="来源平台（默认 alipay）",
    )
    parser.add_argument(
        "--no-actions",
        action="store_true",
        help="禁用 ActionLog 记录",
    )

    return parser.parse_args()


def _format_fund_mapping(mapping: dict[str, tuple[str, str]]) -> None:
    """格式化基金映射摘要。"""
    log("")
    log("📋 基金映射摘要:")
    for fund_name, (fund_code, fund_full_name) in sorted(mapping.items()):
        log(f"   ✅ {fund_name}")
        log(f"      → {fund_code} ({fund_full_name})")


def _format_error_summary(error_summary: dict[str, int]) -> None:
    """格式化错误分类统计。"""
    log("")
    log("📊 错误分类统计:")
    for error_type, count in sorted(error_summary.items()):
        log(f"   [{error_type}]: {count} 笔")


def _format_failed_records(failed_records: list[ImportRecord]) -> None:
    """格式化失败记录详情（按类型分组）。"""
    log("")
    log("❌ 失败记录详情:")

    # 1. 按 error_type 分组
    grouped: dict[str, list[ImportRecord]] = {}
    for record in failed_records:
        grouped.setdefault(record.error_type, []).append(record)

    # 2. 输出每类错误（每类只显示前 3 条）
    for error_type, records in sorted(grouped.items()):
        log(f"\n   [{error_type}] ({len(records)} 笔):")
        for record in records[:3]:
            log(f"     • {record.raw_fund_name}: {record.error_message}")
        if len(records) > 3:
            log(f"     ... 还有 {len(records) - 3} 条")


def _format_result(result: ImportResult, mode: str) -> None:
    """格式化并输出导入结果。

    Args:
        result: 导入结果。
        mode: 导入模式（dry-run / apply）。
    """
    # 1. 输出基本统计
    if mode == "dry-run":
        log("✅ 检查完成")
        log(f"   总计: {result.total} 笔")
        log(f"   可导入: {result.succeeded} 笔")
        log(f"   失败: {result.failed} 笔")
        log(f"   跳过: {result.skipped} 笔")
    else:
        log("✅ 导入完成")
        log(f"   总计: {result.total} 笔")
        log(f"   成功: {result.succeeded} 笔")
        log(f"   失败: {result.failed} 笔")
        log(f"   跳过: {result.skipped} 笔")
        log(f"   成功率: {result.success_rate:.1%}")

    # 1.5 输出 Batch ID（v0.4.3 新增，仅 apply 模式）
    if mode == "apply" and result.batch_id is not None:
        log(f"   📦 Batch ID: {result.batch_id}")

    # 2. 输出降级提示
    if result.downgraded > 0:
        log(f"   ⚠️  降级为 pending: {result.downgraded} 笔（NAV 暂缺，后续自动确认）")

    # 3. 输出基金映射摘要
    if result.fund_mapping:
        _format_fund_mapping(result.fund_mapping)

    # 4. 输出错误统计
    if result.error_summary:
        _format_error_summary(result.error_summary)

    # 5. 输出失败记录详情
    if result.failed_records:
        _format_failed_records(result.failed_records)


def _do_import(args: argparse.Namespace) -> int:
    """执行导入命令。

    Returns:
        退出码：0=成功；4=参数错误；5=其他失败。
    """
    try:
        # 1. 解析参数
        csv_path = args.csv
        mode = "dry_run" if args.mode == "dry-run" else "apply"
        with_actions = not args.no_actions

        # 2. 输出操作提示
        log(f"📥 历史账单导入（{args.mode} 模式）")
        log(f"   CSV 文件: {csv_path}")
        log(f"   来源平台: {args.source}")
        log(f"   记录行为: {'是' if with_actions else '否'}")
        log("")

        # 3. 调用 Flow 函数
        result = import_trades_from_csv(
            csv_path=csv_path,
            source=args.source,
            mode=mode,
            with_actions=with_actions,
        )

        # 4. 格式化输出
        _format_result(result, args.mode)

        return 0
    except FileNotFoundError as err:
        log(f"❌ 文件不存在：{err}")
        return 4
    except ValueError as err:
        log(f"❌ 参数错误：{err}")
        return 4
    except NotImplementedError as err:
        log(f"⚠️  {err}")
        log("")
        log("提示：历史导入功能正在开发中，当前只完成了接口设计。")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 导入失败：{err}")
        return 5


def main() -> int:
    """
    历史账单导入 CLI。

    Returns:
        退出码：0=成功；4=参数错误；5=其他失败。
    """
    # 1. 解析参数
    args = _parse_args()

    # 2. 执行导入
    return _do_import(args)


if __name__ == "__main__":
    sys.exit(main())
