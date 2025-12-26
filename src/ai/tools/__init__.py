"""
AI 工具函数模块。

包含：
- facts: 事实类工具（查库）
- calcs: 计算类工具（纯函数）

使用说明：
    导入此模块会自动注册所有工具到全局注册表。

    from src.ai import tools  # 触发注册
    from src.ai.registry import get_all_tools

    tools_map = get_all_tools()  # 获取已注册的工具
"""

# 导入以触发 @tool 装饰器注册
from src.ai.tools import calcs, facts

__all__ = ["facts", "calcs"]
