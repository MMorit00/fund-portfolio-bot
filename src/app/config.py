from __future__ import annotations

import os


def get_discord_webhook() -> str:
    """
    返回 Discord Webhook 地址。

    - 从环境变量 DISCORD_WEBHOOK_URL 读取
    - 若未配置，抛出错误
    """

    value = os.getenv("DISCORD_WEBHOOK_URL")
    if not value:
        raise RuntimeError("未配置 DISCORD_WEBHOOK_URL 环境变量")
    return value


def get_db_path() -> str:
    """返回 SQLite DB 路径，默认 data/portfolio.db。"""
    return os.getenv("DB_PATH", "data/portfolio.db")


def get_nav_data_source() -> str:
    """净值数据源：eastmoney/tiantian，默认 eastmoney。"""
    return os.getenv("NAV_DATA_SOURCE", "eastmoney")


def enable_sql_debug() -> bool:
    """是否打印 SQL（开发期可打开）。"""
    return os.getenv("ENABLE_SQL_DEBUG", "0") == "1"


TIMEZONE = "Asia/Shanghai"

