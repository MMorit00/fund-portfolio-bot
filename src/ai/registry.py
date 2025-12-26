"""
AI 工具注册装饰器。

职责：
- 提供 @tool 装饰器绑定 Pydantic 参数模型
- 维护全局工具注册表
- 自动生成 OpenAI Function Calling Schema

设计原则：
- Type-Driven：通过 Pydantic 模型自动生成 JSON Schema
- 类型安全：调用时自动验证参数
- 单一注册表：所有工具统一管理

使用示例：
    from src.ai.registry import tool
    from src.ai.schemas.arguments import FundQueryArgs

    @tool(FundQueryArgs)
    def query_fund_nav(fund_code: str, query_date: str | None = None):
        '''查询基金净值'''
        ...

    # 获取所有工具的 OpenAI Schema
    schemas = get_tool_schemas()
"""

from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

# 全局工具注册表：函数名 -> 包装后的函数
_TOOLS_REGISTRY: dict[str, Callable[..., Any]] = {}

T = TypeVar("T")


def tool(args_model: type[BaseModel]) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    工具装饰器：绑定 Pydantic 参数模型到函数。

    Args:
        args_model: Pydantic 模型类，定义工具的入参 Schema。

    Returns:
        装饰器函数。

    功能：
    1. 自动使用 Pydantic 验证入参
    2. 将函数注册到全局工具表
    3. 绑定元数据（args_model, tool_name, description）

    示例：
        @tool(FundQueryArgs)
        def query_fund_nav(fund_code: str, query_date: str | None = None):
            '''查询基金净值'''
            ...

    注意：
        - 函数的 docstring 会作为工具描述
        - 参数名必须与 Pydantic 模型字段一致
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(**kwargs: Any) -> T:
            # 使用 Pydantic 验证参数
            try:
                validated = args_model(**kwargs)
                return func(**validated.model_dump())
            except ValidationError as e:
                logger.error(f"[AIRegistry] 参数验证失败: {func.__name__} - {e}")
                raise

        # 绑定元数据
        wrapper.args_model = args_model  # type: ignore[attr-defined]
        wrapper.tool_name = func.__name__  # type: ignore[attr-defined]
        wrapper.description = func.__doc__ or ""  # type: ignore[attr-defined]

        # 注册到全局表
        _TOOLS_REGISTRY[func.__name__] = wrapper
        logger.debug(f"[AIRegistry] 注册工具: {func.__name__}")

        return wrapper

    return decorator


def get_all_tools() -> dict[str, Callable[..., Any]]:
    """
    获取所有已注册的工具。

    Returns:
        工具名 -> 工具函数的映射表副本。

    示例：
        tools = get_all_tools()
        result = tools["query_fund_nav"](fund_code="000001")
    """
    return _TOOLS_REGISTRY.copy()


def get_tool_schemas() -> list[dict[str, Any]]:
    """
    生成所有工具的 OpenAI Function Calling Schema。

    Returns:
        符合 OpenAI tools 参数格式的列表。

    示例：
        schemas = get_tool_schemas()
        # [{"type": "function", "function": {...}}, ...]

    Schema 格式：
        {
            "type": "function",
            "function": {
                "name": "query_fund_nav",
                "description": "查询基金净值",
                "parameters": {...}  # Pydantic 自动生成
            }
        }
    """
    schemas = []
    for name, func in _TOOLS_REGISTRY.items():
        schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": func.description.strip(),  # type: ignore[attr-defined]
                "parameters": func.args_model.model_json_schema(),  # type: ignore[attr-defined]
            },
        }
        schemas.append(schema)
    return schemas


def clear_registry() -> None:
    """
    清空工具注册表（仅用于测试）。

    警告：生产环境不应调用此函数。
    """
    _TOOLS_REGISTRY.clear()
    logger.warning("[AIRegistry] 工具注册表已清空")
