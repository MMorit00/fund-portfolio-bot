"""持仓市值查询 CLI。"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from src.core.log import log
from src.flows.market_value import MarketValueResult, cal_market_value


def _parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        prog="python -m src.cli.market_value",
        description="持仓市值查询",
    )
    parser.add_argument(
        "--as-of",
        type=str,
        help="查询日期（YYYY-MM-DD）",
    )
    parser.add_argument(
        "--estimate",
        action="store_true",
        help="使用估值回退",
    )
    return parser.parse_args()


def _parse_date(date_str: str) -> date | None:
    """解析日期字符串。

    Args:
        date_str: 日期字符串（YYYY-MM-DD）。

    Returns:
        解析成功返回 date 对象，失败返回 None。
    """
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        log(f"❌ 日期格式错误：{date_str}，正确格式：YYYY-MM-DD")
        return None


def _format_output(result: MarketValueResult) -> None:
    """格式化输出市值结果。

    Args:
        result: 市值查询结果。
    """
    # 1. 输出标题和总市值
    log(f"\n📊 持仓市值（{result.as_of}）\n")
    log(f"总市值: ¥{result.total_market_value:,.2f}")
    log(f"待确认: ¥{result.pending_amount:,.2f}\n")

    # 2. 输出数据来源统计
    log("数据来源统计:")
    log(f"  - 官方净值: {result.official_nav_count} 只基金")
    if result.estimated_nav_count > 0:
        log(f"  - 估值顶替: {result.estimated_nav_count} 只基金")
    if result.missing_nav_count > 0:
        log(f"  - 净值缺失: {result.missing_nav_count} 只基金 ⚠️")
    log("")

    # 3. 输出基金明细
    if result.holdings:
        log("基金明细:\n")
        for h in result.holdings:
            nav_str = f"{h.nav:.4f} [{h.nav_source}]" if h.nav else "N/A"
            mv_str = f"¥{h.market_value:,.2f}" if h.market_value else "N/A"
            log(f"  {h.fund_name} ({h.fund_code})")
            log(f"    份额: {h.shares:,.2f}  净值: {nav_str}  市值: {mv_str}")
            if h.estimated_time:
                log(f"    估值时间: {h.estimated_time}")
            log("")
    else:
        log("暂无持仓\n")

    # 4. 输出说明信息
    if result.estimated_nav_count > 0:
        log("说明: [估] 表示盘中估值，仅供参考\n")
    if result.missing_nav_count > 0:
        log(f"⚠️  {result.missing_nav_count} 只基金净值缺失，建议运行 fetch_navs\n")


def _do_query(args: argparse.Namespace) -> int:
    """执行市值查询命令。

    Args:
        args: 命令行参数。

    Returns:
        退出码：0=成功；4=参数错误。
    """
    # 1. 解析日期
    as_of: date | None = None
    if args.as_of:
        as_of = _parse_date(args.as_of)
        if as_of is None:
            return 4

    # 2. 输出查询提示
    log(f"[MarketValue] 查询日期: {as_of or '上一交易日'}, 估值: {args.estimate}")

    # 3. 调用 Flow 函数
    result = cal_market_value(as_of=as_of, use_estimate=args.estimate)

    # 4. 格式化输出
    _format_output(result)

    return 0


def main() -> int:
    """
    持仓市值查询 CLI。

    Returns:
        退出码：0=成功；4=参数错误。
    """
    # 1. 解析参数
    args = _parse_args()

    # 2. 执行查询
    return _do_query(args)


if __name__ == "__main__":
    sys.exit(main())
