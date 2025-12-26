"""
AI 工具入参 Schema（Pydantic 模型）。

职责：
- 定义 AI 工具的入参结构
- 自动生成 OpenAI Function Calling 的 parameters Schema
- 提供参数验证

设计原则：
- 字段描述清晰，供 LLM 理解
- 使用 pattern 约束格式（如基金代码 6 位）
- 可选字段提供合理默认值
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class NavArgs(BaseModel):
    """
    查询基金净值参数。

    用于 get_nav 工具。
    """

    fund_code: str = Field(
        ...,
        pattern=r"^\d{6}$",
        description="6位数字基金代码，如 000001",
    )
    query_date: str | None = Field(
        None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="查询日期 YYYY-MM-DD，默认为最新",
    )


class ActionArgs(BaseModel):
    """
    查询行为流水参数。

    用于 get_action 工具，从 ActionLog 获取投资行为记录。
    """

    fund_code: str = Field(
        ...,
        pattern=r"^\d{6}$",
        description="6位数字基金代码",
    )
    period: Literal["1m", "3m", "6m", "ytd"] = Field(
        "1m",
        description="查询周期：1m=近1月, 3m=近3月, 6m=近6月, ytd=今年以来",
    )


class RestrictionArgs(BaseModel):
    """
    查询限额参数。

    用于 get_restriction 工具。
    """

    fund_code: str = Field(
        ...,
        pattern=r"^\d{6}$",
        description="6位数字基金代码",
    )
    query_date: str | None = Field(
        None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="查询日期 YYYY-MM-DD，默认为今天",
    )
