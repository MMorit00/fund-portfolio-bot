"""
通用 AI 客户端（OpenAI 兼容协议）。

职责：
- 封装 OpenAI SDK，支持多模型供应商
- 处理 Tool Calls 的完整流程
- 提供重试机制和错误处理

设计原则：
- Model Agnostic：通过环境变量切换供应商
- Structured Output：强制 JSON 输出
- 安全边界：敏感信息不记录日志

支持的供应商：
- 智谱 GLM-4-Flash（默认）
- 阿里 Qwen-Max
- DeepSeek
- 本地 Ollama

使用示例：
    from src.ai.client import AIClient

    client = AIClient()
    response = client.chat("天弘余额宝最近的定投情况如何？")
    print(response)
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any

from openai import APIError, APITimeoutError, OpenAI, RateLimitError

from src.ai.registry import get_all_tools, get_tool_schemas
from src.core.config import AIConfig

logger = logging.getLogger(__name__)

# 查询日志截断长度（敏感信息保护）
_QUERY_LOG_LIMIT = 50


class AIClient:
    """
    通用 AI 客户端（OpenAI 兼容协议）。

    通过环境变量控制接入方，代码零修改切换模型：
    - LLM_BASE_URL: API 端点
    - LLM_API_KEY: API 密钥
    - LLM_MODEL: 模型名称

    Attributes:
        client: OpenAI SDK 客户端实例。
        model: 当前使用的模型名称。
        max_retries: 最大重试次数。

    示例：
        client = AIClient()
        response = client.chat("查询基金 000001 的净值")
    """

    def __init__(self) -> None:
        """
        初始化 AI 客户端。

        Raises:
            ValueError: LLM_API_KEY 未配置。
        """
        self.client = OpenAI(
            api_key=AIConfig.get_api_key(),
            base_url=AIConfig.get_base_url(),
            timeout=AIConfig.get_timeout(),
        )
        self.model = AIConfig.get_model()
        self.max_retries = AIConfig.get_max_retries()
        self._debug = AIConfig.is_debug()

        logger.info(f"[AIClient] 初始化完成，模型: {self.model}")

    def _call_with_retry(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """
        带指数退避的重试机制。

        Args:
            func: 要调用的函数。
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            函数返回值。

        Raises:
            最后一次失败的异常。

        重试策略：
        - RateLimitError: 指数退避（2^attempt 秒）
        - APITimeoutError: 立即重试
        - 5xx 错误: 等待 1 秒后重试
        - 4xx 错误: 不重试，直接抛出
        """
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except RateLimitError as e:
                last_error = e
                wait_time = 2**attempt
                logger.warning(
                    f"[AIClient] 触发限流，等待 {wait_time}s 后重试 ({attempt + 1}/{self.max_retries})"
                )
                time.sleep(wait_time)
            except APITimeoutError as e:
                last_error = e
                logger.warning(f"[AIClient] 请求超时，重试 ({attempt + 1}/{self.max_retries})")
            except APIError as e:
                last_error = e
                # APIError 可能有 status_code 属性（取决于具体子类）
                status = getattr(e, "status_code", None)
                if status and status >= 500:
                    logger.warning(
                        f"[AIClient] 服务端错误 {status}，重试 ({attempt + 1}/{self.max_retries})"
                    )
                    time.sleep(1)
                else:
                    raise  # 4xx 错误不重试

        if last_error:
            raise last_error
        raise RuntimeError("[AIClient] 重试耗尽但无错误记录")

    def chat(
        self,
        query: str,
        *,
        tools_map: dict[str, Any] | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """
        执行对话。

        Args:
            query: 用户查询。
            tools_map: 工具映射表，默认使用全局注册的工具。
            system_prompt: 系统提示词，默认使用内置提示词。

        Returns:
            AI 响应（JSON 字符串或纯文本）。

        流程：
        1. 构建消息（注入当前日期）
        2. 初次调用 LLM
        3. 如有 Tool Calls，执行工具并收集结果
        4. 二次调用 LLM，获取最终分析

        示例：
            response = client.chat("天弘余额宝最近的定投情况如何？")
        """
        if tools_map is None:
            tools_map = get_all_tools()

        # 1. 构建系统提示词
        if system_prompt is None:
            # 延迟导入，避免循环依赖
            from src.ai.prompts.system import get_system_prompt

            system_prompt = get_system_prompt()

        # 注入当前日期
        current_context = f"\n\nCurrent Date: {datetime.now().strftime('%Y-%m-%d')}"
        system_content = system_prompt + current_context

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": query},
        ]

        # 2. 构建工具定义
        tool_schemas = get_tool_schemas() if tools_map else None

        # 3. 初次调用
        query_log = query[:_QUERY_LOG_LIMIT] + "..." if len(query) > _QUERY_LOG_LIMIT else query
        logger.info(f"[AIClient] 发送查询: {query_log}")

        response = self._call_with_retry(
            self.client.chat.completions.create,
            model=self.model,
            messages=messages,
            tools=tool_schemas,
            temperature=0.1,  # 金融场景低温
        )

        msg = response.choices[0].message

        # 4. 处理 Tool Calls
        if msg.tool_calls:
            messages.append(msg)  # type: ignore[arg-type]

            for tool_call in msg.tool_calls:
                func_name = tool_call.function.name
                logger.info(f"[AIClient] 调用工具: {func_name}")

                try:
                    args = json.loads(tool_call.function.arguments)
                    if func_name in tools_map:
                        result = tools_map[func_name](**args)
                    else:
                        result = {"error": f"未知工具: {func_name}"}
                except json.JSONDecodeError as e:
                    result = {"error": f"参数解析失败: {e}"}
                except Exception as e:
                    logger.error(f"[AIClient] 工具执行失败: {func_name} - {e}")
                    result = {"error": str(e), "hint": "请检查参数或稍后重试"}

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

            # 5. 二次调用，获取最终分析
            final_resp = self._call_with_retry(
                self.client.chat.completions.create,
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},  # 强制 JSON
            )
            return final_resp.choices[0].message.content or ""

        return msg.content or ""

    def simple_chat(self, query: str) -> str:
        """
        简单对话（无工具调用）。

        Args:
            query: 用户查询。

        Returns:
            AI 响应（纯文本）。

        说明：用于验证连接或简单问答，不加载工具。
        """
        return self.chat(query, tools_map={})
