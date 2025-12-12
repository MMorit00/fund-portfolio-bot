"""导出导入批次的 DCA 事实快照。

用法：
    python -m src.cli.dca_facts batch <batch_id> [--format table|json]
    python -m src.cli.dca_facts fund <batch_id> <fund_code> [--format table|json]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from src.core.log import log
from src.flows.dca_backfill import build_facts, summarize


def _parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="查看导入批次的 DCA 事实快照",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    batch_parser = subparsers.add_parser("batch", help="查看批次内基金的概览")
    batch_parser.add_argument("batch_id", type=int, help="导入批次 ID")
    batch_parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="输出格式：table/json（默认 table）",
    )

    fund_parser = subparsers.add_parser("fund", help="查看单只基金的详细事实")
    fund_parser.add_argument("batch_id", type=int, help="导入批次 ID")
    fund_parser.add_argument("fund_code", help="基金代码")
    fund_parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="输出格式：table/json（默认 table）",
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


def _format_summary_table(summary_list: list) -> None:
    """打印批次概览。"""
    if not summary_list:
        log("（无数据）")
        return

    log("📦 批次基金概览")
    log("=" * 70)
    header = f"{'Fund':<10} {'Buys':<6} {'Range':<25} {'Mode Amt':<12} {'Anomalies':<10}"
    log(header)
    log("-" * 70)
    for row in summary_list:
        range_str = (
            f"{row.start}~{row.end}"
            if row.start and row.end
            else "-"
        )
        mode_str = str(row.mode_amt) if row.mode_amt else "-"
        log(
            f"{row.code:<10} "
            f"{row.buys:<6} "
            f"{range_str:<25} "
            f"{mode_str:<12} "
            f"{row.anomaly_count:<10}"
        )


def _format_fund_facts_table(facts) -> None:
    """人类可读的单基金展示。"""
    log(f"\n🔹 {facts.code} | 买入 {facts.buys} 笔 / 卖出 {facts.sells} 笔")

    # 时间
    log(f"   时间: {facts.first} → {facts.last} ({facts.days} 天)")

    # 全局模式
    if facts.mode_amt:
        log(f"   众数金额: {facts.mode_amt} 元")
    if facts.mode_gap:
        log(f"   众数间隔: {facts.mode_gap} 天")

    # Top amounts
    if facts.top_amts:
        top_str = ", ".join(f"{amt}×{cnt}" for amt, cnt in facts.top_amts)
        log(f"   Top 金额: {top_str}")

    # Buckets
    if facts.buckets:
        bucket_str = ", ".join(f"{b.label}:{b.count}({b.pct:.0%})" for b in facts.buckets)
        log(f"   金额分布: {bucket_str}")

    # Gaps
    if facts.gaps:
        gap_str = ", ".join(f"{k}:{v}" for k, v in facts.gaps.items())
        log(f"   间隔分布: {gap_str}")

    # Weekdays
    if facts.weekdays:
        weekday_str = ", ".join(f"{k}:{v}" for k, v in facts.weekdays.items())
        log(f"   周期分布: {weekday_str}")

    # Limit
    if facts.limit:
        log(f"   当前限额: {facts.limit} 元")

    # Segments
    if facts.segments:
        log("   📊 稳定片段:")
        for seg in facts.segments:
            log(f"      段{seg.id}: {seg.start}~{seg.end} | {seg.count}笔 | 金额≈{seg.amount} 间隔≈{seg.gap}天")
            if seg.samples:
                samples_str = ", ".join(f"{d}:{amt}" for d, amt in seg.samples[:3])
                log(f"         示例: {samples_str}")

    # Anomalies
    if facts.anomaly_total > 0:
        log(f"   ⚠️ 异常: 共 {facts.anomaly_total} 笔")
        for a in facts.anomalies:
            trades_str = ",".join(str(t) for t in a.trades)
            log(f"      • {a.day} [{a.kind}] trades={trades_str} {a.note}")
    else:
        log("   异常: 无")


def _do_batch(args: argparse.Namespace) -> int:
    try:
        facts_list = build_facts(batch_id=args.batch_id)
        summary = summarize(facts_list)
        if args.format == "json":
            payload = {"batch_id": args.batch_id, "funds": summary}
            print(json.dumps(_to_serializable(payload), ensure_ascii=False, indent=2))
        else:
            _format_summary_table(summary)
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 生成批次概览失败：{err}")
        return 5


def _do_fund(args: argparse.Namespace) -> int:
    try:
        facts_list = build_facts(batch_id=args.batch_id, fund_codes=[args.fund_code])
        if not facts_list:
            log("（未找到对应基金或无数据）")
            return 0

        facts = facts_list[0]
        if args.format == "json":
            payload = {"batch_id": args.batch_id, "facts": facts}
            print(json.dumps(_to_serializable(payload), ensure_ascii=False, indent=2))
        else:
            _format_fund_facts_table(facts)
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 生成基金事实失败：{err}")
        return 5


def main() -> int:
    args = _parse_args()
    if args.command == "batch":
        return _do_batch(args)
    if args.command == "fund":
        return _do_fund(args)
    log("未知命令")
    return 4


if __name__ == "__main__":
    sys.exit(main())
