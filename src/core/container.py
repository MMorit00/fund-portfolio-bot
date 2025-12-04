"""
依赖容器模块（Dependency Container）。

职责：
- 集中管理所有依赖对象的创建逻辑
- 通过 @register 装饰器注册到依赖注入容器
- 为 Flow 函数提供自动依赖注入支持

设计原则：
- 单一职责：只负责创建依赖对象
- 单例模式：数据库连接等资源复用
- 工厂模式：每个依赖都有对应的工厂函数

使用方式：
    # 1. 在 Flow 函数中自动注入
    @dependency
    def confirm_trades(trade_repo=None, nav_service=None):
        # trade_repo 和 nav_service 自动创建
        pass

    # 2. 在 CLI 中直接调用工厂函数
    trade_repo = get_trade_repo()

    # 3. 测试时手动传入 Mock
    confirm_trades(trade_repo=MockTradeRepo())

注意事项：
    - 工厂函数名应清晰表达返回的对象类型
    - @register 的名字必须与 Flow 函数参数名一致
    - 单例资源（如数据库连接）应在模块级缓存
    - 本模块在 src/flows/__init__.py 中自动导入，确保注册表在任何 Flow 使用前被填充
"""

from __future__ import annotations

import sqlite3

from src.core.dependency import register
from src.data.client.discord import DiscordClient
from src.data.client.eastmoney import EastmoneyClient
from src.data.client.local_nav import LocalNavService
from src.data.db.action_repo import ActionRepo
from src.data.db.alloc_config_repo import AllocConfigRepo
from src.data.db.calendar import CalendarService
from src.data.db.db_helper import DbHelper
from src.data.db.dca_plan_repo import DcaPlanRepo
from src.data.db.fund_fee_repo import FundFeeRepo
from src.data.db.fund_repo import FundRepo
from src.data.db.import_batch_repo import ImportBatchRepo
from src.data.db.nav_repo import NavRepo
from src.data.db.trade_repo import TradeRepo

# ========== 全局单例（连接复用） ==========

_db_connection: sqlite3.Connection | None = None


def get_db_connection() -> sqlite3.Connection:
    """
    获取数据库连接（单例模式）。

    Returns:
        SQLite 连接对象。

    说明：
        - 首次调用时初始化 Schema
        - 后续调用复用同一连接
        - CLI 程序退出时自动释放
    """
    global _db_connection
    if _db_connection is None:
        db_helper = DbHelper()
        db_helper.init_schema_if_needed()
        _db_connection = db_helper.get_connection()
    return _db_connection


# ========== 依赖工厂函数（注册到容器） ==========


@register("calendar_service")
def get_calendar_service() -> CalendarService:
    """
    获取交易日历服务。

    Returns:
        交易日历服务实例。

    注册名：calendar_service
    """
    conn = get_db_connection()
    return CalendarService(conn)


@register("db_helper")
def get_db_helper() -> DbHelper:
    """
    获取 DbHelper 实例（用于 Flow 层直接操作数据库）。

    Returns:
        DbHelper 实例（内部按配置的 DB_PATH 管理 SQLite 连接）。

    注册名：db_helper
    """
    return DbHelper()


@register("trade_repo")
def get_trade_repo() -> TradeRepo:
    """
    获取交易仓储。

    Returns:
        交易仓储实例（包含 Calendar 依赖）。

    注册名：trade_repo
    """
    conn = get_db_connection()
    calendar = get_calendar_service()
    return TradeRepo(conn, calendar)


@register("nav_repo")
def get_nav_repo() -> NavRepo:
    """
    获取净值仓储。

    Returns:
        净值仓储实例。

    注册名：nav_repo
    """
    conn = get_db_connection()
    return NavRepo(conn)


@register("fund_repo")
def get_fund_repo() -> FundRepo:
    """
    获取基金仓储。

    Returns:
        基金仓储实例。

    注册名：fund_repo
    """
    conn = get_db_connection()
    return FundRepo(conn)


@register("fund_fee_repo")
def get_fund_fee_repo() -> FundFeeRepo:
    """
    获取基金费率仓储。

    Returns:
        基金费率仓储实例。

    注册名：fund_fee_repo
    """
    conn = get_db_connection()
    return FundFeeRepo(conn)


@register("dca_plan_repo")
def get_dca_plan_repo() -> DcaPlanRepo:
    """
    获取定投计划仓储。

    Returns:
        定投计划仓储实例。

    注册名：dca_plan_repo
    """
    conn = get_db_connection()
    return DcaPlanRepo(conn)


@register("nav_service")
def get_local_nav_service() -> LocalNavService:
    """
    获取本地净值查询服务。

    Returns:
        本地净值查询服务实例（包含 NavRepo 依赖）。

    注册名：nav_service
    """
    nav_repo = get_nav_repo()
    return LocalNavService(nav_repo)


@register("eastmoney_service")
def get_eastmoney_client() -> EastmoneyClient:
    """
    获取东方财富 API 客户端。

    Returns:
        东方财富客户端实例。

    注册名：eastmoney_service
    """
    return EastmoneyClient()


@register("discord_service")
def get_discord_client() -> DiscordClient:
    """
    获取 Discord 客户端。

    Returns:
        Discord 客户端实例。

    注册名：discord_service
    """
    return DiscordClient()


@register("alloc_config_repo")
def get_alloc_config_repo() -> AllocConfigRepo:
    """
    获取资产配置仓储。

    Returns:
        资产配置仓储实例。

    注册名：alloc_config_repo
    """
    conn = get_db_connection()
    return AllocConfigRepo(conn)


@register("action_repo")
def get_action_repo() -> ActionRepo:
    """
    获取行为日志仓储。

    Returns:
        行为日志仓储实例。

    注册名：action_repo
    """
    conn = get_db_connection()
    return ActionRepo(conn)


@register("import_batch_repo")
def get_import_batch_repo() -> ImportBatchRepo:
    """
    获取导入批次仓储（v0.4.3 新增）。

    Returns:
        导入批次仓储实例。

    注册名：import_batch_repo

    说明：
        用于历史导入的批次追溯和撤销，不影响手动/自动交易。
    """
    conn = get_db_connection()
    return ImportBatchRepo(conn)
