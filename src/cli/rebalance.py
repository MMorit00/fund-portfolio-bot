from __future__ import annotations

import argparse
import sys
from datetime import date

from src.core.container import get_calendar_service
from src.core.log import log
from src.core.models.nav import NavQuality
from src.flows.report import make_rebalance_suggestion


def _prev_trading_day(ref: date, market: str = "CN_A") -> date:
    """
    获取上一交易日（使用 CalendarService，严格交易日历）。

    Args:
        ref: 参考日期。
        market: 市场标识（默认 CN_A）。

    Returns:
        上一交易日。

    Raises:
        RuntimeError: 若日历数据缺失。
    """
    calendar = get_calendar_service()
    # 从前一天开始向前找最近交易日
    prev_day = calendar.prev_open(market, ref, lookback=15)
    if prev_day is None:
        raise RuntimeError(f"未能找到 {ref} 之前的交易日（15天内），请检查 trading_calendar 表数据")
    return prev_day


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
        as_of = date.fromisoformat(as_of_arg) if as_of_arg else _prev_trading_day(date.today())

        log(f"[Job:rebalance] 开始：as_of={as_of}")

        # 直接调用 Flow 函数（依赖自动创建）
        result = make_rebalance_suggestion(today=as_of)

        # 格式化输出
        print(f"\n📊 再平衡建议（{as_of}）\n")

        if result.no_market_data:
            print(f"⚠️ {result.note}\n")
            log("[Job:rebalance] 结束（无市场数据）")
            return 0

        print(f"总市值：¥{result.total_value:,.2f}")

        # 显示数据质量摘要（v0.3.3 阶段 3）
        if result.nav_quality_summary:
            quality_counts: dict[NavQuality, int] = {}
            for quality in result.nav_quality_summary.values():
                quality_counts[quality] = quality_counts.get(quality, 0) + 1

            quality_notes: list[str] = []
            if quality_counts.get(NavQuality.holiday, 0) > 0:
                quality_notes.append(
                    f"{quality_counts[NavQuality.holiday]}只基金使用最近交易日数据（周末/节假日）"
                )
            if quality_counts.get(NavQuality.delayed, 0) > 0:
                quality_notes.append(
                    f"⚠️ {quality_counts[NavQuality.delayed]}只基金 NAV 延迟（建议谨慎参考）"
                )

            if quality_notes:
                print(f"数据质量：{', '.join(quality_notes)}")

        print()
        print("当前资产配置：")

        for advice in result.suggestions:
            percentage = advice.current_weight * 100
            target_pct = advice.target_weight * 100
            diff_pct = advice.weight_diff * 100

            if advice.action == "hold":
                print(f"  {advice.asset_class.value}: {percentage:.1f}% (目标 {target_pct:.1f}%) ✓ 正常")
            else:
                action_text = "偏低" if advice.action == "buy" else "偏高"
                emoji = "⚠️" if abs(diff_pct) > 5 else "💡"
                print(
                    f"  {advice.asset_class.value}: {percentage:.1f}% "
                    f"(目标 {target_pct:.1f}%) {emoji} {action_text} {abs(diff_pct):.1f}%"
                )

        print("\n调仓建议：")
        has_action = False
        for advice in result.suggestions:
            if advice.action != "hold":
                has_action = True
                action_text = "建议买入" if advice.action == "buy" else "建议卖出"
                print(f"  {advice.asset_class.value}：{action_text} ¥{advice.amount:,.0f}")

                # 显示具体基金建议（阶段 2 完成后启用）
                fund_list = result.fund_suggestions.get(advice.asset_class, [])
                if fund_list:
                    for fs in fund_list:
                        print(
                            f"    • [{fs.fund_code}] {fs.fund_name}：¥{fs.amount:,.0f} "
                            f"(当前占比 {fs.current_pct*100:.1f}%)"
                        )

        if not has_action:
            print("  无需调仓，当前配置在目标范围内 ✓")

        # 显示跳过基金提示（v0.3.3 阶段 3）
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
