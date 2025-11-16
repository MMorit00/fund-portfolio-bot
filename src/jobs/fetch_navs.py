from __future__ import annotations

import sys
from src.app.log import log


def main() -> int:
    """
    抓取净值任务入口（占位）。

    说明（v0.2 严格版）：
    - 当前项目以本地 `navs` 表为主数据源（由 `dev_seed_db.py` 或手工 upsert 填充）。
    - 本入口仅预留“外部数据源抓取”的装配位置，未来可切换为 Eastmoney 等 Provider。
    - 预计在后续版本中补充：超时/重试/缓存策略与批量落库逻辑。

    Returns:
        退出码：0=成功；4=参数/实现错误。
    """
    try:
        log("[Job] fetch_navs 开始")
        # TODO: 装配 provider+repo，抓取当日 NAV（占位）
        log("[Job] fetch_navs 结束")
        return 0
    except Exception as err:  # noqa: BLE001
        print("执行失败：fetch_navs", err)
        return 4


if __name__ == "__main__":
    sys.exit(main())
