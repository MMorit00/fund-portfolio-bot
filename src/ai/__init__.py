"""
AI 基础架构模块（v0.5.0+）。

职责：
- 提供 OpenAI 兼容协议的 LLM 客户端
- 管理 AI 工具函数的注册与调用
- 定义结构化输入输出 Schema

架构原则：
- Model Agnostic：通过环境变量切换模型供应商
- Type-Driven：Pydantic 自动生成 Schema
- Structured Output：强制 JSON 输出，CLI 负责渲染

目录结构：
    ai/
    ├─ client.py       # AIClient（OpenAI wrapper）
    ├─ registry.py     # @tool 装饰器 & 注册表
    ├─ schemas/        # Pydantic 数据模型
    │   ├─ arguments.py   # 工具入参
    │   └─ responses.py   # AI 输出
    ├─ tools/          # 工具函数实现
    │   ├─ facts.py       # 事实类（查库）
    │   └─ calcs.py       # 计算类（纯函数）
    └─ prompts/        # 系统提示词
        └─ system.py

使用示例：
    from src.ai.client import AIClient

    client = AIClient()
    response = client.chat("天弘余额宝最近的定投情况如何？")
    print(response)
"""

from src.ai.client import AIClient
from src.ai.registry import get_all_tools, get_tool_schemas, tool

__all__ = ["AIClient", "tool", "get_all_tools", "get_tool_schemas"]
