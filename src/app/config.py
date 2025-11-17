from __future__ import annotations

import os


def get_discord_webhook() -> str:
    """
    返回 Discord Webhook 地址。

    Returns:
        Webhook URL 字符串。

    说明：从环境变量 `DISCORD_WEBHOOK_URL` 读取；未配置将抛出错误。
    """

    value = os.getenv("DISCORD_WEBHOOK_URL")
    if not value:
        raise RuntimeError("未配置 DISCORD_WEBHOOK_URL 环境变量")
    return value


def get_db_path() -> str:
    """
    返回 SQLite DB 路径。

    Returns:
        数据库文件路径；默认 `data/portfolio.db`（可由 `DB_PATH` 覆盖）。
    """
    return os.getenv("DB_PATH", "data/portfolio.db")


def get_nav_data_source() -> str:
    """
    返回净值数据源标识。

    Returns:
        `eastmoney`/`tiantian` 等，默认 `eastmoney`（由 `NAV_DATA_SOURCE` 配置）。
    """
    return os.getenv("NAV_DATA_SOURCE", "eastmoney")


def enable_sql_debug() -> bool:
    """
    是否启用 SQL 打印（开发期可打开）。

    Returns:
        True/False（由 `ENABLE_SQL_DEBUG=1` 控制）。
    """
    return os.getenv("ENABLE_SQL_DEBUG", "0") == "1"


TIMEZONE = "Asia/Shanghai"


def get_trading_calendar_backend() -> str:
    """
    返回交易日历后端类型："simple" 或 "db"。

    - 未设置时默认 "simple"；
    - 显式设置为 "db" 时，要求存在 trading_calendar 表，否则视为配置错误。
    """
    return os.getenv("TRADING_CALENDAR_BACKEND", "simple").lower()
