from __future__ import annotations

import os

from src.core.protocols import ReportProtocol


class DiscordReportSender(ReportProtocol):
    """
    Discord Webhook 发送器（占位）。
    MVP 阶段可使用 requests/httpx 发送文本消息。
    """

    def __init__(self, webhook_url: str | None = None) -> None:
        """
        初始化发送器。

        Args:
            webhook_url: 可显式传入 Webhook 地址；为空时从环境变量读取。
        """
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")

    def send(self, text: str) -> bool:  # type: ignore[override]
        """
        发送文本消息到 Discord。

        Args:
            text: 文本内容。

        Returns:
            是否发送成功（占位实现：仅打印并返回 True/False）。

        副作用：可能进行网络请求（未来实现）。
        """
        if not self.webhook_url:
            print("[Notify] 未配置 DISCORD_WEBHOOK_URL，跳过发送")
            return False
        # TODO: 发送 HTTP 请求
        print("[Notify] 发送到 Discord：\n" + text)
        return True
