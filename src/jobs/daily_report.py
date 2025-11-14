from __future__ import annotations

import sys
from src.app.log import log


def main() -> int:
    try:
        log("[Job] daily_report 开始")
        # TODO: 装配 GenerateDailyReport 并发送
        log("[Job] daily_report 结束")
        return 0
    except Exception as err:  # noqa: BLE001
        print("执行失败：daily_report", err)
        return 5


if __name__ == "__main__":
    sys.exit(main())

