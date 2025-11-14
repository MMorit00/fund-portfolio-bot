from __future__ import annotations

import sys
from datetime import date

from src.app.log import log


def main() -> int:
    try:
        log("[Job] confirm_trades 开始")
        today = date.today()
        # TODO: 装配 ConfirmPendingTrades 并执行
        log("[Job] confirm_trades 结束")
        return 0
    except Exception as err:  # noqa: BLE001
        print("执行失败：confirm_trades", err)
        return 5


if __name__ == "__main__":
    sys.exit(main())

