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


# ========== AI 配置（v0.5.0+） ==========


class AIConfig:
    """
    AI 相关配置（OpenAI 兼容协议）。

    支持的模型供应商：
    - 智谱 GLM-4-Flash（默认，免费/低成本）
    - 阿里 Qwen-Max
    - DeepSeek
    - 本地 Ollama

    环境变量：
    - LLM_BASE_URL: API 端点（默认智谱）
    - LLM_API_KEY: API 密钥
    - LLM_MODEL: 模型名称（默认 glm-4-flash）
    - LLM_MAX_RETRIES: 最大重试次数（默认 3）
    - LLM_TIMEOUT: 请求超时秒数（默认 30）
    - LLM_DEBUG: 是否启用调试日志（默认 false）
    """

    @staticmethod
    def get_base_url() -> str:
        """返回 LLM API 端点。"""
        return os.getenv("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")

    @staticmethod
    def get_api_key() -> str:
        """
        返回 LLM API 密钥。

        Raises:
            ValueError: 未配置 LLM_API_KEY 环境变量。
        """
        key = os.getenv("LLM_API_KEY")
        if not key:
            raise ValueError("LLM_API_KEY 环境变量未设置")
        return key

    @staticmethod
    def get_model() -> str:
        """返回 LLM 模型名称。"""
        return os.getenv("LLM_MODEL", "glm-4-flash")

    @staticmethod
    def get_max_retries() -> int:
        """返回最大重试次数。"""
        return int(os.getenv("LLM_MAX_RETRIES", "3"))

    @staticmethod
    def get_timeout() -> float:
        """返回请求超时秒数。"""
        return float(os.getenv("LLM_TIMEOUT", "30"))

    @staticmethod
    def is_debug() -> bool:
        """返回是否启用调试模式。"""
        return os.getenv("LLM_DEBUG", "false").lower() == "true"
