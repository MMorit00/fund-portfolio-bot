"""
AI Schema 模块。

包含：
- arguments: 工具入参 Pydantic 模型
- responses: AI 输出 Pydantic 模型
"""

from src.ai.schemas.arguments import ActionArgs, NavArgs, RestrictionArgs
from src.ai.schemas.responses import FinancialAnalysis

__all__ = [
    "NavArgs",
    "ActionArgs",
    "RestrictionArgs",
    "FinancialAnalysis",
]
