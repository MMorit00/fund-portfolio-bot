"""
AI 输出 Schema（Pydantic 模型）。

职责：
- 定义 AI 响应的结构化格式
- 提供响应验证
- 支持 CLI 渲染

设计原则：
- 字段语义明确
- 支持降级（missing_data 字段）
- 风险等级可枚举
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FinancialAnalysis(BaseModel):
    """
    AI 投资分析的标准输出结构。

    所有 AI 分析响应都应符合此格式，便于 CLI 统一渲染。

    Attributes:
        summary: 简短的事实陈述（1-2 句），包含关键数据。
        analysis: 深度分析，解释数据背后的原因。
        advice: 行动建议（仅供参考，不含具体买卖指令）。
        risk_level: 风险等级评估。
        missing_data: 分析中缺失的数据项列表。
    """

    summary: str = Field(
        ...,
        description="简短的事实陈述，包含关键数据",
    )
    analysis: str = Field(
        ...,
        description="深度分析，解释数据背后的原因",
    )
    advice: str = Field(
        ...,
        description="具体的行动建议（注意：不包含具体买卖指令，仅作为参考）",
    )
    risk_level: Literal["low", "medium", "high"] = Field(
        ...,
        description="风险等级评估",
    )
    missing_data: list[str] = Field(
        default_factory=list,
        description="分析中缺失的数据项，如有",
    )
