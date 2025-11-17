from __future__ import annotations

import argparse
import sys
from datetime import date

from src.app.log import log
from src.app.wiring import DependencyContainer
from src.usecases.marketdata.fetch_navs_for_day import FetchNavsForDay


def _parse_date(value: str | None) -> date:
    """
    解析命令行日期参数。

    Args:
        value: 日期字符串（YYYY-MM-DD）或 None。

    Returns:
        解析后的日期；None 时返回今天。

    Raises:
        ValueError: 日期格式非法。
    """
    if not value:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"日期格式无效：{value}（期望：YYYY-MM-DD）") from exc


def parse_args() -> argparse.Namespace:
    """
    解析 fetch_navs 命令行参数。

    支持参数：
    - --date：目标日期（YYYY-MM-DD），默认今天。
    """
    parser = argparse.ArgumentParser(
        prog="python -m src.jobs.fetch_navs",
        description="从外部数据源抓取基金净值并落库",
    )
    parser.add_argument(
        "--date",
        help="目标日期（格式：YYYY-MM-DD，默认今天）",
    )
    return parser.parse_args()


def main() -> int:
    """
    抓取净值任务入口（调用 UseCase）。

    说明：
    - 遍历当前 DB 中已配置的全部基金，按指定日期调用 EastmoneyNavProvider 获取 NAV；
    - 对获取成功且 NAV>0 的记录调用 NavRepo.upsert，保证按 (fund_code, day) 幂等；
    - 对失败/无效的记录仅计入失败列表并打印日志，不中断整体流程。

    Returns:
        退出码：0=成功；4=参数/实现错误。
    """
    try:
        args = parse_args()
        target_day = _parse_date(getattr(args, "date", None))

        log(f"[Job] fetch_navs 开始：day={target_day}")

        with DependencyContainer() as container:
            uc: FetchNavsForDay = container.get_fetch_navs_usecase()
            result = uc.execute(day=target_day)

        log(
            f"[Job] fetch_navs 结束：day={result.day} total={result.total} "
            f"success={result.success} failed={len(result.failed_codes)}"
        )
        if result.failed_codes:
            log(
                "[Job] fetch_navs 失败基金代码（部分可能因 NAV 缺失或网络错误）： "
                + ", ".join(sorted(result.failed_codes))
            )
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"执行失败：fetch_navs {err}")
        return 4


if __name__ == "__main__":
    sys.exit(main())
