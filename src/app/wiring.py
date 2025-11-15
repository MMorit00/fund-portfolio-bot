from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal
from typing import Optional

from src.adapters.db.sqlite.alloc_config_repo import SqliteAllocConfigRepo
from src.adapters.db.sqlite.dca_plan_repo import SqliteDcaPlanRepo
from src.adapters.db.sqlite.db_helper import SqliteDbHelper
from src.adapters.db.sqlite.fund_repo import SqliteFundRepo
from src.adapters.db.sqlite.nav_repo import SqliteNavRepo
from src.adapters.db.sqlite.trade_repo import SqliteTradeRepo
from src.adapters.notify.discord_report import DiscordReportSender
from src.app import config
from src.usecases.dca.run_daily import RunDailyDca
from src.usecases.dca.skip_date import SkipDcaForDate
from src.usecases.portfolio.daily_report import GenerateDailyReport
from src.usecases.trading.confirm_pending import ConfirmPendingTrades
from src.usecases.trading.create_trade import CreateTrade


class LocalNavProvider:
    """
    本地 NavProvider 实现（方案 A）：从 NavRepo 读取 NAV。
    不做 HTTP 抓取，仅依赖 dev_seed_db 或手工写入的数据。
    """

    def __init__(self, nav_repo: SqliteNavRepo) -> None:
        self.nav_repo = nav_repo

    def get_nav(self, fund_code: str, day: date) -> Optional[Decimal]:
        """从本地 NavRepo 获取指定日期的净值。"""
        return self.nav_repo.get(fund_code, day)


class DependencyContainer:
    """
    依赖容器：管理 DB 连接、仓储、UseCase 的生命周期。
    使用上下文管理器确保 DB 连接正确关闭。
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or config.get_db_path()
        self.helper: Optional[SqliteDbHelper] = None
        self.conn: Optional[sqlite3.Connection] = None

        # 仓储实例
        self.fund_repo: Optional[SqliteFundRepo] = None
        self.trade_repo: Optional[SqliteTradeRepo] = None
        self.nav_repo: Optional[SqliteNavRepo] = None
        self.dca_repo: Optional[SqliteDcaPlanRepo] = None
        self.alloc_repo: Optional[SqliteAllocConfigRepo] = None

        # 适配器实例
        self.nav_provider: Optional[LocalNavProvider] = None
        self.discord_sender: Optional[DiscordReportSender] = None

    def __enter__(self) -> "DependencyContainer":
        """初始化数据库连接与仓储。"""
        self.helper = SqliteDbHelper(str(self.db_path))
        self.helper.init_schema_if_needed()
        self.conn = self.helper.get_connection()

        # 初始化仓储
        self.fund_repo = SqliteFundRepo(self.conn)
        self.trade_repo = SqliteTradeRepo(self.conn)
        self.nav_repo = SqliteNavRepo(self.conn)
        self.dca_repo = SqliteDcaPlanRepo(self.conn)
        self.alloc_repo = SqliteAllocConfigRepo(self.conn)

        # 初始化适配器
        self.nav_provider = LocalNavProvider(self.nav_repo)
        self.discord_sender = DiscordReportSender()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        """关闭数据库连接。"""
        if self.helper:
            self.helper.close()

    def get_create_trade_usecase(self) -> CreateTrade:
        """获取 CreateTrade UseCase。"""
        if not self.trade_repo or not self.fund_repo:
            raise RuntimeError("容器未初始化，请在 with 块中使用")
        return CreateTrade(self.trade_repo, self.fund_repo)

    def get_run_daily_dca_usecase(self) -> RunDailyDca:
        """获取 RunDailyDca UseCase。"""
        if not self.dca_repo or not self.fund_repo or not self.trade_repo:
            raise RuntimeError("容器未初始化，请在 with 块中使用")
        return RunDailyDca(self.dca_repo, self.fund_repo, self.trade_repo)

    def get_skip_dca_usecase(self) -> SkipDcaForDate:
        """获取 SkipDcaForDate UseCase。"""
        if not self.dca_repo or not self.trade_repo:
            raise RuntimeError("容器未初始化，请在 with 块中使用")
        return SkipDcaForDate(self.dca_repo, self.trade_repo)

    def get_confirm_pending_trades_usecase(self) -> ConfirmPendingTrades:
        """获取 ConfirmPendingTrades UseCase。"""
        if not self.trade_repo or not self.nav_provider:
            raise RuntimeError("容器未初始化，请在 with 块中使用")
        return ConfirmPendingTrades(self.trade_repo, self.nav_provider)

    def get_daily_report_usecase(self) -> GenerateDailyReport:
        """获取 GenerateDailyReport UseCase。"""
        if (
            not self.alloc_repo
            or not self.trade_repo
            or not self.fund_repo
            or not self.discord_sender
            or not self.nav_provider
        ):
            raise RuntimeError("容器未初始化，请在 with 块中使用")
        return GenerateDailyReport(
            self.alloc_repo,
            self.trade_repo,
            self.fund_repo,
            self.nav_provider,
            self.discord_sender,
        )
