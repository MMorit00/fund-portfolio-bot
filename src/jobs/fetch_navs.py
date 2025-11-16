from __future__ import annotations

import sys
from src.app.log import log


def main() -> int:
    """
    抓取净值任务入口（占位）：装配 provider+repo 拉取当日 NAV。

    Returns:
        退出码：0=成功；4=参数/实现错误。
    """
    try:
        log("[Job] fetch_navs 开始")
        # TODO: 装配 provider+repo，抓取当日 NAV
        log("[Job] fetch_navs 结束")
        return 0
    except Exception as err:  # noqa: BLE001
        print("执行失败：fetch_navs", err)
        return 4


if __name__ == "__main__":
    sys.exit(main())
