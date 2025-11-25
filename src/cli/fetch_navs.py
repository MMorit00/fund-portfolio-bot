from __future__ import annotations

import argparse
import sys
from datetime import date

from src.core.container import get_calendar_service
from src.core.log import log
from src.flows.market import fetch_navs


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


def _parse_date(value: str | None) -> date:
    """
    解析命令行日期参数。

    Args:
        value: 日期字符串（YYYY-MM-DD）或 None。

    Returns:
        解析后的日期；None 时返回上一交易日（更稳定，因为基金NAV通常当日晚上才公布）。

    Raises:
        ValueError: 日期格式非法。
        RuntimeError: 日历数据缺失。
    """
    if not value:
        return _prev_trading_day(date.today())
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"日期格式无效：{value}（期望：YYYY-MM-DD）") from exc


def parse_args() -> argparse.Namespace:
    """
    解析 fetch_navs 命令行参数。

    支持参数：
    - --date：目标日期（YYYY-MM-DD），默认上一交易日。
    - --funds：指定基金代码列表（逗号分隔），可选。
    - --auto-detect-missing：自动检测延迟交易的缺失 NAV 并补抓。
    - --days：auto-detect-missing 时检测的天数范围，默认 30 天。
    """
    parser = argparse.ArgumentParser(
        prog="python -m src.cli.fetch_navs",
        description="从外部数据源抓取基金净值并落库",
    )
    parser.add_argument(
        "--date",
        help="目标日期（格式：YYYY-MM-DD，默认上一交易日，因当日NAV通常晚上才公布）",
    )
    parser.add_argument(
        "--funds",
        help="指定基金代码列表（逗号分隔，如：000001,110022），不指定时抓取所有基金",
    )
    parser.add_argument(
        "--auto-detect-missing",
        action="store_true",
        help="自动检测延迟交易的缺失 NAV 并补抓（忽略 --date 和 --funds）",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="--auto-detect-missing 时检测的天数范围（默认 30 天）",
    )
    return parser.parse_args()


def main() -> int:
    """
    抓取净值任务入口。

    说明：
    - 模式 1（默认）：遍历当前 DB 中已配置的全部基金（或指定基金），按指定日期调用 EastmoneyNavProvider 获取 NAV；
    - 模式 2（--auto-detect-missing）：自动检测延迟交易的缺失 NAV 并补抓；
    - 对获取成功且 NAV>0 的记录调用 NavRepo.upsert，保证按 (fund_code, day) 幂等；
    - 对失败/无效的记录仅计入失败列表并打印日志，不中断整体流程。

    Returns:
        退出码：0=成功；4=参数/实现错误。
    """
    try:
        args = parse_args()

        # 模式 1：自动检测缺失 NAV
        if args.auto_detect_missing:
            log(f"[Job:fetch_navs] 自动检测模式：扫描最近 {args.days} 天的延迟交易")
            result = fetch_navs(auto_detect_missing=True, days=args.days)
            log(
                f"[Job:fetch_navs] 补抓结束：total={result.total} "
                f"success={result.success} failed={len(result.failed_codes)}"
            )
            if result.failed_codes:
                log(
                    "[Job:fetch_navs] 补抓失败（部分可能因 NAV 缺失或网络错误）： "
                    + ", ".join(sorted(result.failed_codes))
                )
            return 0

        # 模式 2：按日期抓取
        target_day = _parse_date(getattr(args, "date", None))

        # 解析 --funds 参数（逗号分隔的基金代码列表）
        fund_codes: list[str] | None = None
        if args.funds:
            fund_codes = [code.strip() for code in args.funds.split(",") if code.strip()]
            log(f"[Job:fetch_navs] 开始：day={target_day} funds={fund_codes}")
        else:
            log(f"[Job:fetch_navs] 开始：day={target_day} funds=全部")

        # 直接调用 Flow 函数（依赖自动创建）
        result = fetch_navs(day=target_day, fund_codes=fund_codes)

        log(
            f"[Job:fetch_navs] 结束：day={result.day} total={result.total} "
            f"success={result.success} failed={len(result.failed_codes)}"
        )
        if result.failed_codes:
            log(
                "[Job:fetch_navs] 失败基金代码（部分可能因 NAV 缺失或网络错误）： "
                + ", ".join(sorted(result.failed_codes))
            )
            # 如果抓今日NAV且失败较多，给出友好提示
            if result.day == date.today() and len(result.failed_codes) > result.success:
                log("⚠️  提示：今日 NAV 可能尚未公布（通常 18:00-22:00 后可抓取），建议晚上重试")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 执行失败：fetch_navs - {err}")
        return 4


if __name__ == "__main__":
    sys.exit(main())
