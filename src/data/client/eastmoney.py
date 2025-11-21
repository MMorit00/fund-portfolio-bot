from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from time import sleep
from urllib.parse import urlencode

import httpx


class EastmoneyNavService:
    """
    东方财富 NAV 数据源服务（骨架实现）。

    设计原则：
    - 仅负责"单只基金单日 NAV 的 HTTP 获取与解析"，不直接落库；
    - 所有网络/解析异常均被捕获并记录，返回 None，由上层决定是否重试/告警；
    - 使用 httpx 同步 Client，支持超时与有限重试（指数退避）。

    说明：
    - 当前版本仅提供结构化骨架，具体 API URL 与字段解析留待后续实现；
    - 真实接入时建议参考东方财富公开接口，填充 `_build_url` 与 `_parse_nav`。
    """

    def __init__(
        self,
        *,
        timeout: float = 3.0,
        retries: int = 2,
        base_url: str | None = None,
        user_agent: str | None = None,
        backoff_base: float = 0.2,
    ) -> None:
        """
        初始化东方财富 NAV Provider。

        Args:
            timeout: 单次请求超时时间（秒）。
            retries: 最大重试次数（>=0）；不包含初次请求，如 retries=2 则最多尝试 3 次（1 次初次 + 2 次重试）。
            base_url: 东方财富接口基础地址（可选，未填时使用默认占位）。
            user_agent: 自定义 User-Agent 头（可选）。
            backoff_base: 重试指数退避基础间隔（秒），实际等待约为 base * 2^attempt。
        """
        if retries < 0:
            raise ValueError("retries 必须 >= 0")
        self.timeout = timeout
        self.retries = retries
        # 东方财富历史净值 REST 接口（按日查询）
        # 示例：
        # https://api.fund.eastmoney.com/f10/lsjz?fundCode=110022&pageIndex=1&pageSize=1&startDate=2025-11-20&endDate=2025-11-20
        self.base_url = base_url or "https://api.fund.eastmoney.com/f10/lsjz"
        self.user_agent = (
            user_agent
            or "fund-portfolio-bot/0.1 (+https://github.com/your-repo-or-homepage)"
        )
        self.backoff_base = backoff_base

    def get_nav(self, fund_code: str, day: date) -> Decimal | None:
        """
        读取东方财富的官方单位净值（骨架实现）。

        当前实现行为：
        - 根据基金代码与日期构造请求 URL；
        - 在有限次数内重试 HTTP 请求；
        - 尝试从响应中解析 NAV 字段并转为 Decimal；
        - 任一环节异常时记录简要信息并返回 None，不抛出异常。

        Args:
            fund_code: 基金代码。
            day: 净值日期。

        Returns:
            若成功获取且 NAV>0 则返回 Decimal 净值；否则返回 None。
        """
        url = self._build_url(fund_code, day)
        headers = {
            "User-Agent": self.user_agent,
            # Eastmoney 对 Referer 比较敏感，缺失可能返回 403/空数据
            "Referer": "https://fundf10.eastmoney.com/",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }

        attempt = 0
        while True:
            try:
                data = self._fetch_raw_json(url, headers=headers)
                if data is None:
                    return None
                nav = self._parse_nav(data)
                if nav is None or nav <= Decimal("0"):
                    print(
                        f"[EastmoneyNav] 无效 NAV 数据：fund={fund_code} day={day} data={data!r}"
                    )
                    return None
                return nav
            except Exception as err:  # noqa: BLE001
                # 防御性兜底：不向上抛异常，避免打断批量任务
                print(
                    f"[EastmoneyNav] 获取 NAV 失败：fund={fund_code} day={day} attempt={attempt} err={err}"
                )
                if attempt >= self.retries:
                    return None
                attempt += 1
                sleep(self.backoff_base * (2**attempt))

    def _build_url(self, fund_code: str, day: date) -> str:
        """
        构造东方财富净值查询 URL（占位实现）。

        说明：
        - 真实接入时应根据具体 API 规则拼接查询参数（如代码、日期范围等）。
        """
        # f10/lsjz 接口支持 startDate/endDate，按同一天精确取 1 条
        params = {
            "fundCode": fund_code,
            "pageIndex": 1,
            "pageSize": 1,
            "startDate": day.isoformat(),
            "endDate": day.isoformat(),
        }
        return f"{self.base_url}?{urlencode(params)}"

    def _fetch_raw_json(self, url: str, *, headers: dict[str, str]) -> dict | None:
        """
        发起 HTTP GET 并返回 JSON。

        行为说明：
        - 5xx/429：调用 `raise_for_status()` 抛出 HTTPStatusError，交由外层重试；
        - 其它非 200：记录一条提示并返回 None（不重试）；
        - 200：返回解析后的 JSON；若 JSON 解析失败（ValueError），返回 None。
        """
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(url, headers=headers)
            # 需要重试的错误让其抛出，由外层重试逻辑处理
            if resp.status_code >= 500 or resp.status_code == 429:
                resp.raise_for_status()
            if resp.status_code != 200:
                print(
                    f"[EastmoneyNav] HTTP 状态异常：status={resp.status_code} url={url}"
                )
                return None
            try:
                return resp.json()
            except ValueError as err:
                print(f"[EastmoneyNav] JSON 解析失败：url={url} err={err}")
                return None

    def _parse_nav(self, raw: dict) -> Decimal | None:
        """
        从东方财富响应中解析单位净值（占位实现）。

        说明：
        - 当前仅为结构占位，假设 raw 中存在某个字段存放净值；
        - 真实接入时请根据实际字段名做解析。
        """
        # 典型返回结构（示意）：
        # {
        #   "ErrCode": 0,
        #   "Data": {
        #       "LSJZList": [ {"FSRQ": "2025-11-20", "DWJZ": "1.2345", ...} ],
        #       ...
        #   }
        # }
        data = raw.get("Data") or raw.get("data")
        if not isinstance(data, dict):
            return None
        items = data.get("LSJZList") or data.get("lsjzList") or data.get("Datas")
        if not isinstance(items, list) or not items:
            return None
        item = items[0]
        if not isinstance(item, dict):
            return None
        nav_str = item.get("DWJZ") or item.get("dwjz")
        if not nav_str:
            return None
        try:
            return Decimal(str(nav_str))
        except (InvalidOperation, TypeError):
            return None
