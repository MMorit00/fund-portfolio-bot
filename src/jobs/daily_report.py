from __future__ import annotations

import sys

from src.app.log import log
from src.app.wiring import DependencyContainer


def main() -> int:
    try:
        log("[Job] daily_report 开始")

        with DependencyContainer() as container:
            usecase = container.get_daily_report_usecase()
            success = usecase.send()
            if success:
                log("✅ 日报发送成功")
            else:
                log("⚠️ 日报发送失败（可能未配置 Webhook）")

        log("[Job] daily_report 结束")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 执行失败：daily_report - {err}")
        return 5


if __name__ == "__main__":
    sys.exit(main())

