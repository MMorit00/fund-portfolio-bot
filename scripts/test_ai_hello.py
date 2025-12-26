#!/usr/bin/env python3
"""
快速验证 AI 客户端是否正常工作。

使用方式：
    uv run python scripts/test_ai_hello.py

前置条件：
    设置环境变量 LLM_API_KEY（或在 .env 文件中配置）
"""

from __future__ import annotations

import os
import sys


def test_hello() -> None:
    """验证 AI 客户端基本连接。"""
    # 尝试加载 .env
    try:
        from dotenv import load_dotenv

        load_dotenv()
        print("✓ 已加载 .env 文件")
    except ImportError:
        print("⚠ python-dotenv 未安装，跳过 .env 加载")

    # 检查 API Key
    if not os.getenv("LLM_API_KEY"):
        print("✗ 错误: LLM_API_KEY 环境变量未设置")
        print("  请设置: export LLM_API_KEY=your_api_key")
        sys.exit(1)

    print(f"✓ LLM_BASE_URL: {os.getenv('LLM_BASE_URL', 'https://open.bigmodel.cn/api/paas/v4/')}")
    print(f"✓ LLM_MODEL: {os.getenv('LLM_MODEL', 'glm-4-flash')}")

    # 测试连接
    print("\n正在测试 AI 连接...")

    from src.ai.client import AIClient

    client = AIClient()
    response = client.simple_chat("你好，请用一句话介绍自己")

    print(f"\n📝 AI 响应: {response}")
    assert response, "AI 响应为空"

    print("\n✅ AI 客户端验证通过")


def test_tools_registration() -> None:
    """验证工具注册。"""
    print("\n正在验证工具注册...")

    # 导入 tools 以触发注册
    from src.ai import tools  # noqa: F401
    from src.ai.registry import get_all_tools, get_tool_schemas

    tools_map = get_all_tools()
    schemas = get_tool_schemas()

    print(f"✓ 已注册 {len(tools_map)} 个工具:")
    for name in tools_map:
        print(f"  - {name}")

    print(f"\n✓ 生成 {len(schemas)} 个 OpenAI Schema")

    # 验证必需的工具
    required_tools = ["query_fund_nav", "query_dca_execution", "query_restriction_context"]
    for tool_name in required_tools:
        if tool_name not in tools_map:
            print(f"✗ 缺少必需工具: {tool_name}")
            sys.exit(1)

    print("\n✅ 工具注册验证通过")


if __name__ == "__main__":
    print("=" * 50)
    print("AI 基础架构验证脚本")
    print("=" * 50)

    # 验证工具注册（不需要 API Key）
    test_tools_registration()

    # 验证 AI 连接（需要 API Key）
    if "--skip-api" not in sys.argv:
        test_hello()
    else:
        print("\n⚠ 跳过 API 连接测试（--skip-api）")

    print("\n" + "=" * 50)
    print("所有验证通过！")
    print("=" * 50)
