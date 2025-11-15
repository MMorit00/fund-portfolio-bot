from __future__ import annotations

import sys
from datetime import date

from src.app.log import log
from src.app.wiring import DependencyContainer


def main() -> int:
    try:
        log("[Job] run_dca 开始")
        today = date.today()
        log(f"今日：{today}")

        with DependencyContainer() as container:
            usecase = container.get_run_daily_dca_usecase()
            count = usecase.execute(today=today)
            log(f"✅ 成功生成 {count} 笔定投交易")

        log("[Job] run_dca 结束")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 执行失败：run_dca - {err}")
        return 5


if __name__ == "__main__":
    sys.exit(main())

