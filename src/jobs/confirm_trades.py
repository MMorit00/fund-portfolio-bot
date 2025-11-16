from __future__ import annotations

import sys
from datetime import date

from src.app.log import log
from src.app.wiring import DependencyContainer


def main() -> int:
    """
    确认交易任务入口：按 v0.2 规则与 DB 预写确认日确认当日交易。

    Returns:
        退出码：0=成功；5=未知错误。
    """
    try:
        log("[Job] confirm_trades 开始")
        today = date.today()
        log(f"今日：{today}")

        with DependencyContainer() as container:
            usecase = container.get_confirm_pending_trades_usecase()
            count = usecase.execute(today=today)
            log(f"✅ 成功确认 {count} 笔交易")

        log("[Job] confirm_trades 结束")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 执行失败：confirm_trades - {err}")
        return 5


if __name__ == "__main__":
    sys.exit(main())
