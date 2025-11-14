from __future__ import annotations

import sys
from src.app.log import log


def main() -> int:
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

