from __future__ import annotations

import sqlite3
from typing import Optional

from src.adapters.datasources.eastmoney_nav import EastmoneyNavService
from src.adapters.datasources.local_nav import LocalNavService
from src.adapters.db.sqlite.alloc_config_repo import SqliteAllocConfigRepo
from src.adapters.db.sqlite.calendar import SqliteCalendarService
from src.adapters.db.sqlite.db_helper import SqliteDbHelper
from src.adapters.db.sqlite.dca_plan_repo import SqliteDcaPlanRepo
from src.adapters.db.sqlite.fund_repo import SqliteFundRepo
from src.adapters.db.sqlite.nav_repo import SqliteNavRepo
from src.adapters.db.sqlite.trade_repo import SqliteTradeRepo
from src.adapters.notify.discord_report import DiscordReportService
from src.app import config
from src.core.protocols import CalendarProtocol
from src.usecases.dca.run_daily import RunDailyDca
from src.usecases.dca.skip_date import SkipDcaForDate
from src.usecases.marketdata.fetch_navs_for_day import FetchNavsForDay
from src.usecases.portfolio.daily_report import GenerateDailyReport
from src.usecases.portfolio.rebalance_suggestion import GenerateRebalanceSuggestion
from src.usecases.trading.confirm_pending import ConfirmPendingTrades
from src.usecases.trading.create_trade import CreateTrade


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
        self.nav_provider: Optional[LocalNavService] = None
        self.discord_sender: Optional[DiscordReportService] = None
        self.calendar: Optional[CalendarProtocol] = None

    def __enter__(self) -> "DependencyContainer":
        """初始化数据库连接与仓储。"""
        self.helper = SqliteDbHelper(str(self.db_path))
        self.helper.init_schema_if_needed()
        self.conn = self.helper.get_connection()

        # 初始化仓储
        self.fund_repo = SqliteFundRepo(self.conn)

        # 初始化交易日历服务（v0.3：严格要求 DB 日历）
        backend = config.get_trading_calendar_backend()
        if backend != "db":
            raise RuntimeError(
                "v0.3 要求使用 DB 交易日历，请设置 TRADING_CALENDAR_BACKEND=db "
                "并运行 sync_calendar/patch_calendar 任务"
            )

        # 确认 trading_calendar 表存在
        exists = (
            self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='trading_calendar'"
            ).fetchone()
            is not None
        )
        if not exists:
            raise RuntimeError(
                "TRADING_CALENDAR_BACKEND=db，但未发现 trading_calendar 表，请先执行迁移/导入"
            )

        # 使用统一的 CalendarService
        self.calendar = SqliteCalendarService(self.conn)

        # 初始化适配器与仓储
        self.trade_repo = SqliteTradeRepo(self.conn, self.calendar)
        self.nav_repo = SqliteNavRepo(self.conn)
        self.dca_repo = SqliteDcaPlanRepo(self.conn)
        self.alloc_repo = SqliteAllocConfigRepo(self.conn)

        self.nav_provider = LocalNavService(self.nav_repo)
        self.discord_sender = DiscordReportService()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        """关闭数据库连接。"""
        if self.helper:
            self.helper.close()

    # === UseCase 构造方法 ===

    def get_create_trade_usecase(self) -> CreateTrade:
        """获取 CreateTrade UseCase。"""
        if not self.trade_repo or not self.fund_repo:
            raise RuntimeError("容器未初始化，请在 with 块中使用")
        return CreateTrade(self.trade_repo, self.fund_repo)

    def get_run_daily_dca_usecase(self) -> RunDailyDca:
        """获取 RunDailyDca UseCase。"""
        if not self.dca_repo:
            raise RuntimeError("容器未初始化，请在 with 块中使用")
        create_trade = self.get_create_trade_usecase()
        return RunDailyDca(self.dca_repo, create_trade)

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

    def get_rebalance_suggestion_usecase(self) -> GenerateRebalanceSuggestion:
        """获取 GenerateRebalanceSuggestion UseCase。"""
        if (
            not self.alloc_repo
            or not self.trade_repo
            or not self.fund_repo
            or not self.nav_provider
        ):
            raise RuntimeError("容器未初始化，请在 with 块中使用")
        return GenerateRebalanceSuggestion(
            self.alloc_repo,
            self.trade_repo,
            self.fund_repo,
            self.nav_provider,
        )

    # === 其他 UseCase ===

    def get_fetch_navs_usecase(self) -> FetchNavsForDay:
        """获取 FetchNavsForDay UseCase（Eastmoney Provider）。"""
        if not self.fund_repo or not self.nav_repo:
            raise RuntimeError("容器未初始化，请在 with 块中使用")
        provider = EastmoneyNavService()
        return FetchNavsForDay(self.fund_repo, self.nav_repo, provider)
