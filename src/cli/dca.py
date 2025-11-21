from __future__ import annotations

import sys
from datetime import date

from src.core.log import log
from src.data.db.calendar import CalendarService
from src.data.db.db_helper import DbHelper
from src.data.db.dca_plan_repo import DcaPlanRepo
from src.data.db.fund_repo import FundRepo
from src.data.db.trade_repo import TradeRepo
from src.flows.dca import RunDailyDca
from src.flows.trade import CreateTrade


def run_dca_flow(today: date) -> int:
    """
    定投生成业务流程函数。

    该函数封装了定投生成的完整流程：
    1. 初始化数据库连接和依赖
    2. 调用定投生成用例
    3. 返回生成的交易数量

    Args:
        today: 当日日期

    Returns:
        生成的交易数量
    """
    # 初始化数据库
    db_helper = DbHelper()
    db_helper.init_schema_if_needed()
    conn = db_helper.get_connection()

    # 构造依赖
    calendar = CalendarService(conn)
    dca_repo = DcaPlanRepo(conn)
    fund_repo = FundRepo(conn)
    trade_repo = TradeRepo(conn, calendar)

    # 创建 CreateTrade usecase
    create_trade = CreateTrade(trade_repo, fund_repo)

    # 执行业务逻辑
    usecase = RunDailyDca(dca_repo, create_trade)
    return usecase.execute(today=today)


def main() -> int:
    """
    定投生成任务入口：按计划生成当日 pending 交易。

    Returns:
        退出码：0=成功；5=未知错误。
    """
    try:
        log("[Job] run_dca 开始")
        today = date.today()
        log(f"今日：{today}")

        count = run_dca_flow(today)
        log(f"✅ 成功生成 {count} 笔定投交易")

        log("[Job] run_dca 结束")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 执行失败：run_dca - {err}")
        return 5


if __name__ == "__main__":
    sys.exit(main())
