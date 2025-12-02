from __future__ import annotations

import argparse
import sys
from datetime import date

from src.core.log import log
from src.core.models import NavQuality
from src.flows.report import RebalanceResult, make_rebalance_suggestion


def _format_quality_summary(result: RebalanceResult) -> str | None:
    """格式化 NAV 数据质量摘要。"""
    if not result.nav_quality_summary:
        return None

    quality_counts: dict[NavQuality, int] = {}
    for quality in result.nav_quality_summary.values():
        quality_counts[quality] = quality_counts.get(quality, 0) + 1

    quality_notes: list[str] = []
    if quality_counts.get(NavQuality.holiday, 0) > 0:
        quality_notes.append(f"{quality_counts[NavQuality.holiday]}只基金使用最近交易日数据（周末/节假日）")
    if quality_counts.get(NavQuality.delayed, 0) > 0:
        quality_notes.append(f"⚠️ {quality_counts[NavQuality.delayed]}只基金 NAV 延迟（建议谨慎参考）")

    return f"数据质量：{', '.join(quality_notes)}" if quality_notes else None


def _format_asset_allocation(result: RebalanceResult) -> list[str]:
    """格式化当前资产配置。"""
    lines: list[str] = ["当前资产配置："]
    for advice in result.suggestions:
        percentage = advice.current_weight * 100
        target_pct = advice.target_weight * 100
        diff_pct = advice.weight_diff * 100

        if advice.action == "hold":
            lines.append(f"  {advice.asset_class.value}: {percentage:.1f}% (目标 {target_pct:.1f}%) ✓ 正常")
        else:
            action_text = "偏低" if advice.action == "buy" else "偏高"
            emoji = "⚠️" if abs(diff_pct) > 5 else "💡"
            lines.append(
                f"  {advice.asset_class.value}: {percentage:.1f}% "
                f"(目标 {target_pct:.1f}%) {emoji} {action_text} {abs(diff_pct):.1f}%"
            )
    return lines


def _format_suggestions(result: RebalanceResult) -> list[str]:
    """格式化调仓建议。"""
    lines: list[str] = ["调仓建议："]
    has_action = False

    for advice in result.suggestions:
        if advice.action != "hold":
            has_action = True
            action_text = "建议买入" if advice.action == "buy" else "建议卖出"
            lines.append(f"  {advice.asset_class.value}：{action_text} ¥{advice.amount:,.0f}")

            # 显示具体基金建议
            fund_list = result.fund_suggestions.get(advice.asset_class, [])
            for fs in fund_list:
                lines.append(
                    f"    • [{fs.fund_code}] {fs.fund_name}：¥{fs.amount:,.0f} "
                    f"(当前占比 {fs.current_pct*100:.1f}%)"
                )

    if not has_action:
        lines.append("  无需调仓，当前配置在目标范围内 ✓")

    return lines


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli.rebalance",
        description="生成资产配置再平衡建议（默认上一交易日，使用交易日历）",
    )
    parser.add_argument(
        "--as-of",
        help="展示日（YYYY-MM-DD），默认上一交易日（使用交易日历）",
    )
    return parser.parse_args()


def main() -> int:
    """
    再平衡建议任务入口。

    Returns:
        退出码：0=成功；5=未知错误。
    """
    try:
        args = _parse_args()
        as_of_arg = getattr(args, "as_of", None)
        as_of = date.fromisoformat(as_of_arg) if as_of_arg else None

        log(f"[Job:rebalance] 开始：as_of={as_of or '上一交易日'}")

        # 调用 Flow 函数（as_of=None 时自动使用上一交易日）
        result = make_rebalance_suggestion(today=as_of)

        # 格式化输出（使用 result.as_of 显示实际日期）
        print(f"\n📊 再平衡建议（{result.as_of}）\n")

        if result.no_market_data:
            print(f"⚠️ {result.note}\n")
            log("[Job:rebalance] 结束（无市场数据）")
            return 0

        print(f"总市值：¥{result.total_value:,.2f}")

        # 显示数据质量摘要
        quality_summary = _format_quality_summary(result)
        if quality_summary:
            print(quality_summary)

        # 显示当前资产配置
        print()
        for line in _format_asset_allocation(result):
            print(line)

        # 显示调仓建议
        print()
        for line in _format_suggestions(result):
            print(line)

        # 显示跳过基金提示
        if result.skipped_funds:
            print()
            print(f"⚠️ 以下基金 NAV 持续缺失（未计入）：{', '.join(result.skipped_funds)}")
            print("建议操作：python -m src.cli.fetch_navs --auto-detect-missing")

        print()
        log("[Job:rebalance] 结束")
        return 0

    except Exception as err:  # noqa: BLE001
        log(f"❌ 执行失败：rebalance - {err}")
        return 5


if __name__ == "__main__":
    sys.exit(main())
