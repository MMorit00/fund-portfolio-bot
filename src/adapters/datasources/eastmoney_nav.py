from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from src.usecases.ports import NavProvider


class EastmoneyNavProvider(NavProvider):
    """
    东方财富官方净值数据源适配器（占位）。

    设计预期（后续版本实现）：
    - 使用 httpx/requests 发起 HTTP 请求，超时控制（如连接/读取超时各 3~5 秒）。
    - 简单重试策略（如最多 2 次，指数退避），服务端 5xx 或网络闪断时重试。
    - 结果缓存：同一基金同一天的 NAV 读取缓存（进程内或落地），减少重复请求。
    - 失败处理：按基金/日期粒度返回 None，并由上层决定是否重试/告警。

    v0.2 阶段：项目仍以本地 `navs` 表为主数据源，本适配器仅保留接口占位。
    """

    def get_nav(self, fund_code: str, day: date) -> Optional[Decimal]:  # type: ignore[override]
        """
        读取东方财富的官方单位净值（占位）。

        Args:
            fund_code: 基金代码。
            day: 净值日期。

        Returns:
            若成功获取则返回 Decimal 净值；当前占位实现始终抛出未实现。
        """
        raise NotImplementedError
