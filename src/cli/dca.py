from __future__ import annotations

import sys
from datetime import date

from src.core.log import log
from src.flows.dca import run_daily_dca


def main() -> int:
    """
    定投生成任务入口：按计划生成当日 pending 交易。

    Returns:
        退出码：0=成功；5=未知错误。
    """
    try:
        log("[Job:dca] 开始")
        today = date.today()
        log(f"今日：{today}")

        # 直接调用 Flow 函数（依赖自动创建）
        count = run_daily_dca(today=today)
        log(f"✅ 成功生成 {count} 笔定投交易")

        log("[Job:dca] 结束")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 执行失败：dca - {err}")
        return 5


if __name__ == "__main__":
    sys.exit(main())
