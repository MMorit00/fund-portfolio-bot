"""账单导入 CLI。

用法：
    # 分析模式（只读，输出 BillFacts）
    python -m src.cli.bill analyze <csv> [--format table|json] [--fund <code>]

    # 导入模式（交互式：分析 → 确认 → 写库）
    python -m src.cli.bill import <csv> [--dry-run] [--yes]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from src.core.log import log
from src.flows.bill_facts import build_bill_summary
from src.flows.bill_import import check_funds_exist, import_bill
from src.flows.bill_parser import parse_bill_csv


def _parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="账单导入工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # analyze 命令
    analyze_parser = subparsers.add_parser("analyze", help="分析账单（只读）")
    analyze_parser.add_argument("csv", help="CSV 文件路径")
    analyze_parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="输出格式：table/json（默认 table）",
    )
    analyze_parser.add_argument(
        "--fund",
        help="只分析指定基金代码",
    )

    # import 命令
    import_parser = subparsers.add_parser("import", help="导入账单（交互式）")
    import_parser.add_argument("csv", help="CSV 文件路径")
    import_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览，不写入数据库",
    )
    import_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="跳过确认，直接导入",
    )

    return parser.parse_args()


def _to_serializable(obj: Any) -> Any:
    """递归转换为可 JSON 序列化的结构。"""
    if is_dataclass(obj):
        return _to_serializable(asdict(obj))
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_serializable(v) for v in obj]
    if isinstance(obj, tuple):
        return [_to_serializable(v) for v in obj]
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    return obj


def _format_summary_table(summary) -> None:
    """打印账单汇总。"""
    log("📦 账单汇总")
    log("=" * 70)
    log(f"基金数: {summary.total_funds}")
    log(f"交易数: {summary.total_trades} (定投: {summary.total_dca}, 普通: {summary.total_normal})")
    if summary.first and summary.last:
        log(f"时间范围: {summary.first} → {summary.last}")
    log(f"总申请: {summary.total_apply} 元")
    log(f"总确认: {summary.total_confirm} 元")
    log(f"总手续费: {summary.total_fee} 元")

    if summary.errors:
        log(f"\n⚠️ 解析错误: {len(summary.errors)} 条")
        for err in summary.errors[:5]:
            log(f"   第{err.row_num}行: {err.error_type.value} - {err.message}")
        if len(summary.errors) > 5:
            log(f"   ... 还有 {len(summary.errors) - 5} 条错误")


def _format_facts_table(facts) -> None:
    """打印单基金事实。"""
    log(f"\n🔹 {facts.code} | {facts.name}")
    log(f"   交易: 定投 {facts.dca_count} 笔, 普通 {facts.normal_count} 笔")
    log(f"   时间: {facts.first} → {facts.last}")
    log(f"   金额: 申请 {facts.total_apply} 元, 确认 {facts.total_confirm} 元, 手续费 {facts.total_fee} 元")

    # 阶段
    if facts.phases:
        log("   📊 金额阶段:")
        for i, phase in enumerate(facts.phases, 1):
            if phase.amounts:
                # 同一天多笔不同金额
                amounts_str = ", ".join(str(a) for a in phase.amounts)
                log(
                    f"      {i}. {phase.start} | "
                    f"{phase.count}笔 | 金额=[{amounts_str}]"
                )
            else:
                log(
                    f"      {i}. {phase.start}~{phase.end} | "
                    f"{phase.count}笔 | 申请≈{phase.apply_amt} 确认≈{phase.confirm_amt}"
                )

    # 间隔分布
    if facts.gaps:
        gap_str = ", ".join(f"{k}:{v}" for k, v in facts.gaps.items())
        log(f"   间隔分布: {gap_str}")

    # 周期分布
    if facts.weekdays:
        weekday_str = ", ".join(f"{k}:{v}" for k, v in facts.weekdays.items())
        log(f"   周期分布: {weekday_str}")

    # 异常
    if facts.anomaly_total > 0:
        log(f"   ⚠️ 异常: 共 {facts.anomaly_total} 笔")
        for a in facts.anomalies:
            log(f"      • {a.day} [{a.kind}] {a.note}")


def _do_analyze(args: argparse.Namespace) -> int:
    """执行分析命令。"""
    csv_path = Path(args.csv)
    if not csv_path.exists():
        log(f"❌ 文件不存在: {csv_path}")
        return 1

    # 解析 CSV
    items, errors = parse_bill_csv(csv_path)
    log(f"[BillAnalyze] 解析完成: {len(items)} 条记录, {len(errors)} 个错误")

    # 构建汇总
    summary = build_bill_summary(items, errors)

    # 过滤基金
    if args.fund:
        summary.facts = [f for f in summary.facts if f.code == args.fund]
        if not summary.facts:
            log(f"❌ 未找到基金: {args.fund}")
            return 2

    # 输出
    if args.format == "json":
        print(json.dumps(_to_serializable(summary), ensure_ascii=False, indent=2))
    else:
        _format_summary_table(summary)
        for facts in summary.facts:
            _format_facts_table(facts)

    return 0


def _do_import(args: argparse.Namespace) -> int:
    """执行导入命令。"""
    csv_path = Path(args.csv)
    if not csv_path.exists():
        log(f"❌ 文件不存在: {csv_path}")
        return 1

    # 解析 CSV
    items, errors = parse_bill_csv(csv_path)
    log(f"[BillImport] 解析完成: {len(items)} 条记录, {len(errors)} 个错误")

    if not items:
        log("❌ 没有可导入的记录")
        return 2

    if errors:
        log(f"⚠️ 有 {len(errors)} 个解析错误，这些记录将被跳过")

    # 构建汇总并展示
    summary = build_bill_summary(items, errors)
    _format_summary_table(summary)
    for facts in summary.facts:
        _format_facts_table(facts)

    # 检查基金是否存在
    existing, missing = check_funds_exist(items)
    if missing:
        log("\n⚠️ 以下基金不存在于数据库，将被跳过:")
        for code in missing:
            log(f"   • {code}")

    # 计算可导入数量
    importable = [item for item in items if item.fund_code in existing]
    log(f"\n📊 可导入: {len(importable)} 条 (共 {len(items)} 条)")

    if args.dry_run:
        log("\n[--dry-run] 预览模式，不写入数据库")
        return 0

    # 确认
    if not args.yes:
        log("")
        confirm = input(f"是否导入以上 {len(importable)} 笔交易？[y/N] ")
        if confirm.lower() != "y":
            log("已取消导入")
            return 0

    # 执行导入
    result = import_bill(
        items=importable,
        source="alipay_pdf",
        note=str(csv_path),
    )

    # 显示结果
    log("\n✅ 导入完成!")
    log(f"   批次 ID: {result.batch_id}")
    log(f"   成功: {result.imported}")
    log(f"   跳过: {result.skipped}")
    log(f"   失败: {result.failed}")

    if result.errors:
        log("\n❌ 失败详情:")
        for err in result.errors[:10]:
            log(f"   • {err.fund_code}: {err.error}")
        if len(result.errors) > 10:
            log(f"   ... 还有 {len(result.errors) - 10} 条")

    return 0


def main() -> int:
    """CLI 入口。"""
    args = _parse_args()

    if args.command == "analyze":
        return _do_analyze(args)
    if args.command == "import":
        return _do_import(args)

    log("未知命令")
    return 4


if __name__ == "__main__":
    sys.exit(main())
