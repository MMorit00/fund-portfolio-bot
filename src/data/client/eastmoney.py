from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from time import sleep
from urllib.parse import quote, urlencode

import httpx

from src.core.log import log


@dataclass(slots=True)
class FundSearchResult:
    """
    东方财富基金搜索结果（内部模型）。

    仅在本模块内部使用，用于规整 search_fund 的解析结果。
    """

    fund_code: str
    name: str
    market: str
    ftype: str | None = None
    fund_type_code: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """转换为调用方当前使用的字典形式。"""
        return {
            "fund_code": self.fund_code,
            "name": self.name,
            "market": self.market,
            "ftype": self.ftype,
            "fund_type_code": self.fund_type_code,
        }


class EastmoneyClient:
    """
    东方财富 API 客户端。

    职责：
    - 获取历史官方净值（get_nav）
    - 搜索基金信息（search_fund）
    - 获取盘中估算净值（get_nav_estimate）
    - 获取基金费率信息（get_fund_fees）

    设计原则：
    - 仅负责 HTTP 请求与响应解析，不直接落库；
    - 所有网络/解析异常均被捕获并记录，返回 None，由上层决定是否重试/告警；
    - 使用 httpx 同步 Client，支持超时与有限重试（指数退避）。
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
        初始化东方财富客户端。

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

    # ============================================================
    # 区域：历史官方净值（get_nav / _build_url / _parse_nav）
    # ============================================================

    def get_nav(self, fund_code: str, day: date) -> Decimal | None:
        """
        获取官方确认净值，用于计算仓位、市值和交易确认。

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
                    log(
                        f"[Client:Eastmoney] 无效 NAV 数据：fund={fund_code} day={day}"
                    )
                    return None
                return nav
            except Exception as err:  # noqa: BLE001
                # 防御性兜底：不向上抛异常，避免打断批量任务
                log(
                    "[Client:Eastmoney] 获取 NAV 失败："
                    f"fund={fund_code} day={day} err={err}"
                )
                if attempt >= self.retries:
                    return None
                attempt += 1
                sleep(self.backoff_base * (2**attempt))

    def _build_url(self, fund_code: str, day: date) -> str:
        """
        构造东方财富净值查询 URL。
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
                log(
                    "[Client:Eastmoney] HTTP 状态异常："
                    f"status={resp.status_code} url={url}"
                )
                return None
            try:
                return resp.json()
            except ValueError as err:
                log(f"[Client:Eastmoney] JSON 解析失败：url={url} err={err}")
                return None

    def _parse_nav(self, raw: dict) -> Decimal | None:
        """
        从东方财富响应中解析单位净值。
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

    # ============================================================
    # 区域：基金搜索（search_fund / _do_search / 一组 _search_* 辅助函数）
    # ============================================================

    def search_fund(self, fund_name: str) -> dict | None:
        """
        根据基金名称搜索基金信息。

        搜索策略（三级降级）：
        1. 先尝试完整名称搜索
        2. 若失败，提取核心关键词（去掉括号后缀）重新搜索
        3. 若仍失败，进一步简化（去掉 ETF联接/指数 等后缀）

        份额类型匹配：
        - 从原始名称提取份额类型（A/C/E 等）
        - 遍历搜索结果，优先选择匹配的份额类型

        Args:
            fund_name: 基金名称（支持模糊搜索）。

        Returns:
            基金信息字典 {fund_code, name, market, ftype} 或 None。
        TODO: 后续可考虑返回 FundSearchResult 而非裸 dict，减少 magic string。
        """
        # 提取份额类型（A/C/E 等）
        share_class = self._search_extract_share_class(fund_name)

        # 策略1：先尝试完整名称
        result = self._do_search(fund_name, share_class=share_class)
        if result is not None:
            return result

        # 策略2：提取核心关键词（去掉括号后缀）重试
        core_name = self._search_extract_core_name(fund_name)
        if core_name and core_name != fund_name:
            log(
                "[Client:Eastmoney] 完整名称搜索失败，"
                f"尝试核心关键词：{core_name}"
            )
            result = self._do_search(core_name, share_class=share_class)
            if result is not None:
                return result

        # 策略3：进一步简化（去掉 ETF联接/指数 等后缀）
        simple_name = self._search_simplify_name(core_name or fund_name)
        if simple_name and simple_name != core_name and simple_name != fund_name:
            log(
                "[Client:Eastmoney] 核心关键词搜索失败，"
                f"尝试简化名称：{simple_name}"
            )
            result = self._do_search(simple_name, share_class=share_class)
            if result is not None:
                return result

        return None

    def _do_search(
        self, keyword: str, *, share_class: str | None = None
    ) -> dict | None:
        """
        执行单次搜索（内部方法）。

        Args:
            keyword: 搜索关键词。
            share_class: 期望的份额类型（A/C/E 等），用于在多个结果中选择。
        """
        url = f"https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx?m=1&key={quote(keyword)}"
        headers = {
            "User-Agent": self.user_agent,
            "Referer": "https://fund.eastmoney.com/",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }

        try:
            data = self._fetch_raw_json(url, headers=headers)
            if data is None:
                return None
            result_obj = self._parse_search_result(
                data,
                query=keyword,
                share_class=share_class,
            )
            if result_obj is None:
                return None

            # 过滤明显不匹配的结果（避免 F0xxxx 等误匹配）
            code = result_obj.fund_code
            name = result_obj.name
            if code is None or len(code) != 6 or not str(code).isdigit():
                return None

            # 宽松的关键词匹配
            if not self._search_is_name_match(keyword, name):
                return None

            # 对外仍返回 dict，保持现有调用方不变
            return result_obj.to_dict()
        except Exception as err:  # noqa: BLE001
            log(
                "[Client:Eastmoney] 搜索基金失败："
                f"keyword={keyword} err={err}"
            )
            return None

    @staticmethod
    def _search_extract_share_class(fund_name: str) -> str | None:
        """
        从基金名称中提取份额类型（A/C/E/H/I 等）。

        示例：
        - 「易方达纳斯达克100ETF联接(QDII-LOF)A」→「A」
        - 「易方达纳斯达克100ETF联接(QDII-LOF)C(人民币)」→「C」
        - 「嘉实纳斯达克100ETF发起联接(QDII)A人民币」→「A」
        - 「大成纳斯达克100ETF联接(QDII)C」→「C」
        - 「xxx指数」→ None

        Args:
            fund_name: 基金名称。

        Returns:
            份额类型字母或 None。
        """
        # 在末尾附近查找份额类型：要求前后都不是字母，以避免命中 ETF/QDII/LOF 中的字母
        matches = re.findall(r"(?<![A-Za-z])([A-IY])(?=$|[^A-Za-z])", fund_name)
        if matches:
            return matches[-1]  # 取最末尾的匹配
        return None

    @staticmethod
    def _search_extract_core_name(fund_name: str) -> str:
        """提取基金名称的核心部分（去掉括号后缀）。"""
        match = re.match(r"^([^(（]+)", fund_name)
        if match:
            return match.group(1).strip()
        return fund_name

    @staticmethod
    def _search_simplify_name(fund_name: str) -> str:
        """进一步简化基金名称（去掉 ETF联接/指数 等后缀）。"""
        suffixes = ["ETF联接", "ETF发起联接", "发起联接", "联接", "指数", "ETF"]
        result = fund_name
        for suffix in suffixes:
            if result.endswith(suffix):
                result = result[: -len(suffix)]
                break
        result = re.sub(r"(ETF)?联接$", "", result)
        result = re.sub(r"指数$", "", result)
        return result.strip()

    def _search_is_name_match(self, query: str, result_name: str) -> bool:
        """判断搜索结果名称是否与查询匹配（宽松匹配）。"""
        q_core = self._search_extract_keywords(query)
        r_core = self._search_extract_keywords(result_name)
        if not q_core or not r_core:
            return False
        return q_core in r_core or r_core in q_core

    @staticmethod
    def _search_extract_keywords(name: str) -> str:
        """提取基金名称的核心关键词（去掉修饰词）。"""
        core = re.sub(r"[（(].*$", "", name)
        modifiers = ["发起", "人民币", "美元", "港币", "增强", "增强型"]
        for mod in modifiers:
            core = core.replace(mod, "")
        return core.replace(" ", "").replace("\t", "").lower()

    def _parse_search_result(
        self, raw: dict, *, query: str, share_class: str | None = None
    ) -> FundSearchResult | None:
        """
        从东方财富搜索响应中解析基金信息。

        Args:
            raw: 搜索接口返回的 JSON 数据。
            query: 搜索关键词（未使用，保留兼容）。
            share_class: 期望的份额类型（A/C/E 等），优先选择匹配的结果。

        Returns:
            基金搜索结果或 None（解析失败或无结果）。
        """
        datas = raw.get("Datas")
        if not isinstance(datas, list) or not datas:
            return None

        # 如果指定了份额类型，遍历结果找匹配的；否则取第一个
        selected_item = None
        fallback_item = None  # 后备：第一个有效结果
        for item in datas:
            if not isinstance(item, dict):
                continue
            code = item.get("CODE")
            name = item.get("NAME")
            if not code or not name:
                continue
            # 过滤非标准基金代码
            if len(code) != 6 or not code.isdigit():
                continue

            # 记录第一个有效结果作为后备
            if fallback_item is None:
                fallback_item = item

            # 如果指定了份额类型，检查是否匹配
            if share_class:
                item_class = self._search_extract_share_class(name)
                if item_class == share_class:
                    selected_item = item
                    break  # 找到匹配的份额类型
            else:
                selected_item = item
                break  # 不指定份额类型，取第一个有效结果

        # 如果没有精确匹配，使用后备
        if selected_item is None:
            selected_item = fallback_item

        if selected_item is None:
            return None

        fund_code = selected_item.get("CODE")
        name = selected_item.get("NAME")
        base_info = selected_item.get("FundBaseInfo")

        # 解析 market 和基金类型信息
        market = "CN_A"  # 默认境内基金
        ftype = ""
        fund_type_code = ""

        if isinstance(base_info, dict):
            ftype = base_info.get("FTYPE", "")
            fund_type_code = base_info.get("FUNDTYPE", "")
            if "QDII" in ftype or "海外" in ftype:
                market = "US_NYSE"
        elif isinstance(base_info, str):
            parts = base_info.split("|")
            if parts and "QDII" in parts[0].upper():
                market = "US_NYSE"

        return FundSearchResult(
            fund_code=str(fund_code),
            name=str(name),
            market=str(market),
            ftype=ftype or None,
            fund_type_code=fund_type_code or None,
        )

    # ============================================================
    # 区域：盘中估算净值（get_nav_estimate）
    # ============================================================

    def get_nav_estimate(self, fund_code: str) -> tuple[Decimal, str] | None:
        """
        获取盘中估算净值，仅用于展示与诊断，不参与结算。

        数据源：天天基金 fundgz 接口

        返回：(估算净值, 更新时间) 或 None

        ⚠️ 注意：
        - QDII 基金估值可能不准确（时区、汇率差异）
        - 仅用于最近几天的市值查询验证
        - 不存储到数据库，不用于交易确认

        Args:
            fund_code: 基金代码（6 位数字）

        Returns:
            (估算净值, 估值时间) 或 None
            估值时间格式：YYYY-MM-DD HH:MM
        """
        url = f"http://fundgz.1234567.com.cn/js/{fund_code}.js"
        headers = {
            "User-Agent": self.user_agent,
            "Referer": "http://fund.eastmoney.com/",
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code != 200:
                    log(
                        "[Client:Eastmoney] 获取盘中估值失败："
                        f"fund={fund_code} status={resp.status_code}"
                    )
                    return None

                # 返回格式：jsonpgz({...});
                m = re.search(r"\{.+\}", resp.text)
                if not m:
                    log(
                        "[Client:Eastmoney] 获取盘中估值失败："
                        f"fund={fund_code} 原始响应无法解析"
                    )
                    return None

                data = json.loads(m.group(0))
                gsz = data.get("gsz")  # 估算净值
                gztime = data.get("gztime")  # 估值时间 "2025-11-28 15:00"

                if not gsz or not gztime:
                    log(
                        "[Client:Eastmoney] 获取盘中估值失败："
                        f"fund={fund_code} 缺少必要字段"
                    )
                    return None

                nav = Decimal(str(gsz))
                return nav, gztime

        except json.JSONDecodeError as e:
            log(
                "[Client:Eastmoney] 获取盘中估值失败："
                f"fund={fund_code} JSON 解析错误 {e}"
            )
            return None
        except (InvalidOperation, TypeError, ValueError) as e:
            log(
                "[Client:Eastmoney] 获取盘中估值失败："
                f"fund={fund_code} 数据转换错误 {e}"
            )
            return None
        except Exception as e:
            log(
                "[Client:Eastmoney] 获取盘中估值失败："
                f"fund={fund_code} err={e}"
            )
            return None

    # ============================================================
    # 区域：基金费率信息（get_fund_fees / _parse_redemption_fees / _get_fees_from_js）
    # ============================================================

    def get_fund_fees(self, fund_code: str) -> dict | None:
        """
        获取基金费率信息。

        数据源：东方财富基金费率页面

        返回字典包含：
        - management_fee: 管理费率（年化百分比）
        - custody_fee: 托管费率（年化百分比）
        - service_fee: 销售服务费率（年化百分比）
        - purchase_fee: 申购费率原费率（百分比）
        - purchase_fee_discount: 申购费率折扣后费率（百分比）
        - redemption: 赎回费阶梯列表 [{"min_hold_days": 0, "max_hold_days": 7, "rate": Decimal("1.50")}, ...]

        Args:
            fund_code: 基金代码（6 位数字）

        Returns:
            费率字典或 None（获取失败）

        TODO: 后续可考虑拆分为“获取原始 HTML/JS + 独立解析规则模块”，
        EastmoneyClient 只负责 I/O。
        """
        url = f"http://fundf10.eastmoney.com/jjfl_{fund_code}.html"
        headers = {
            "User-Agent": self.user_agent,
            "Referer": "http://fund.eastmoney.com/",
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code != 200:
                    log(
                        "[Client:Eastmoney] 获取费率失败："
                        f"fund={fund_code} status={resp.status_code}"
                    )
                    return None

                html = resp.text
                fees: dict = {}

                # 解析运作费用
                # 管理费率：0.50%（每年）
                m = re.search(r"管理费率</td><td[^>]*>(\d+\.?\d*)%", html)
                if m:
                    fees["management_fee"] = Decimal(m.group(1))

                # 托管费率：0.10%（每年）
                m = re.search(r"托管费率</td><td[^>]*>(\d+\.?\d*)%", html)
                if m:
                    fees["custody_fee"] = Decimal(m.group(1))

                # 销售服务费率：0.00%（每年）或 ---（无此费用）
                m = re.search(r"销售服务费率</td><td[^>]*>(\d+\.?\d*)%", html)
                if m:
                    fees["service_fee"] = Decimal(m.group(1))
                elif re.search(r"销售服务费率</td><td[^>]*>---", html):
                    fees["service_fee"] = Decimal("0")

                # 解析申购费率（从第一档提取）
                # 格式：<strike class='gray'>1.00%</strike>&nbsp;|&nbsp;0.10%
                m = re.search(
                    r"<strike[^>]*>(\d+\.?\d*)%</strike>.*?\|.*?(\d+\.?\d*)%",
                    html,
                )
                if m:
                    fees["purchase_fee"] = Decimal(m.group(1))
                    fees["purchase_fee_discount"] = Decimal(m.group(2))
                else:
                    # 备用：从 pingzhongdata.js 获取
                    fees_from_js = self._get_fees_from_js(fund_code)
                    if fees_from_js:
                        fees.update(fees_from_js)

                # 解析赎回费阶梯
                redemption_tiers = self._parse_redemption_fees(html)
                if redemption_tiers:
                    fees["redemption"] = redemption_tiers

                if not fees:
                    log(
                        "[Client:Eastmoney] 获取费率失败："
                        f"fund={fund_code} 无法解析费率数据"
                    )
                    return None

                return fees

        except Exception as e:
            log(
                "[Client:Eastmoney] 获取费率失败："
                f"fund={fund_code} err={e}"
            )
            return None

    def _parse_redemption_fees(self, html: str) -> list[dict] | None:
        """
        解析赎回费阶梯（从 HTML 中提取）。

        HTML 格式示例（东方财富）：
        <td>小于等于6天</td><td>1.50%</td>
        <td>大于等于7天，小于等于364天</td><td>0.50%</td>
        <td>大于等于365天，小于等于729天</td><td>0.25%</td>
        <td>大于等于730天</td><td>0.00%</td>

        Returns:
            赎回费阶梯列表或 None（解析失败）

        TODO: 当前使用正则匹配 HTML，如东方财富改版会失效，
        可考虑改用 DOM 解析库或增加备用数据源。
        """
        tiers: list[dict] = []

        # 东方财富常见格式匹配
        # 注意：更具体的模式要放在前面，避免被通用模式先匹配
        patterns = [
            # 格式1: 大于等于X天，小于等于Y天 → rate%（范围格式，需先匹配）
            (
                r"大于等于\s*(\d+)\s*[天日]，小于等于\s*(\d+)\s*[天日]</td><td[^>]*>(\d+\.?\d*)%",
                lambda m: {"min_hold_days": int(m.group(1)), "max_hold_days": int(m.group(2)) + 1, "rate": Decimal(m.group(3))},
            ),
            # 格式2: 大于等于X天，小于Y天 → rate%
            (
                r"大于等于\s*(\d+)\s*[天日]，小于\s*(\d+)\s*[天日]</td><td[^>]*>(\d+\.?\d*)%",
                lambda m: {"min_hold_days": int(m.group(1)), "max_hold_days": int(m.group(2)), "rate": Decimal(m.group(3))},
            ),
            # 格式3: 大于等于X天 → rate%（无上限，单独出现）
            (
                r"(?<!，)大于等于\s*(\d+)\s*[天日]</td><td[^>]*>(\d+\.?\d*)%",
                lambda m: {"min_hold_days": int(m.group(1)), "max_hold_days": None, "rate": Decimal(m.group(2))},
            ),
            # 格式4: 小于等于X天 → rate%（最短期限，排除 "大于等于...，小于等于" 中的）
            (
                r"(?<!，)小于等于\s*(\d+)\s*[天日]</td><td[^>]*>(\d+\.?\d*)%",
                lambda m: {"min_hold_days": 0, "max_hold_days": int(m.group(1)) + 1, "rate": Decimal(m.group(2))},
            ),
            # 格式5: 小于X天 → rate%（最短期限，不含等于）
            (
                r"(?<!，)小于\s*(\d+)\s*[天日]</td><td[^>]*>(\d+\.?\d*)%",
                lambda m: {"min_hold_days": 0, "max_hold_days": int(m.group(1)), "rate": Decimal(m.group(2))},
            ),
            # 格式6: 大于X天 → rate%（无上限，不含等于）
            (
                r"(?<!，)大于\s*(\d+)\s*[天日]</td><td[^>]*>(\d+\.?\d*)%",
                lambda m: {"min_hold_days": int(m.group(1)) + 1, "max_hold_days": None, "rate": Decimal(m.group(2))},
            ),
            # 旧格式兼容: 持有期限<7天
            (
                r"持有期限\s*[<＜]\s*(\d+)\s*[天日].*?(\d+\.?\d*)%",
                lambda m: {"min_hold_days": 0, "max_hold_days": int(m.group(1)), "rate": Decimal(m.group(2))},
            ),
            # 旧格式兼容: X天≤持有期限<Y天
            (
                r"(\d+)\s*[天日]\s*[≤<=]\s*持有期限\s*[<＜]\s*(\d+)\s*[天日].*?(\d+\.?\d*)%",
                lambda m: {"min_hold_days": int(m.group(1)), "max_hold_days": int(m.group(2)), "rate": Decimal(m.group(3))},
            ),
            # 旧格式兼容: 持有期限≥X天
            (
                r"持有期限\s*[≥>=]\s*(\d+)\s*[天日].*?(\d+\.?\d*)%",
                lambda m: {"min_hold_days": int(m.group(1)), "max_hold_days": None, "rate": Decimal(m.group(2))},
            ),
        ]

        found_patterns = set()
        for pattern, extractor in patterns:
            for m in re.finditer(pattern, html):
                tier = extractor(m)
                # 避免重复添加相同区间
                tier_key = (tier["min_hold_days"], tier["max_hold_days"])
                if tier_key not in found_patterns:
                    found_patterns.add(tier_key)
                    tiers.append(tier)

        if not tiers:
            return None

        # 按 min_hold_days 排序
        tiers.sort(key=lambda t: t["min_hold_days"])
        return tiers

    def _get_fees_from_js(self, fund_code: str) -> dict[str, Decimal] | None:
        """从 pingzhongdata.js 获取申购费率（备用方案）。"""
        url = f"http://fund.eastmoney.com/pingzhongdata/{fund_code}.js"
        headers = {
            "User-Agent": self.user_agent,
            "Referer": "http://fund.eastmoney.com/",
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code != 200:
                    return None

                js_content = resp.text
                fees: dict[str, Decimal] = {}

                # var fund_sourceRate="1.00"
                m = re.search(r'fund_sourceRate="(\d+\.?\d*)"', js_content)
                if m:
                    fees["purchase_fee"] = Decimal(m.group(1))

                # var fund_Rate="0.10"
                m = re.search(r'fund_Rate="(\d+\.?\d*)"', js_content)
                if m:
                    fees["purchase_fee_discount"] = Decimal(m.group(1))

                return fees if fees else None

        except Exception:
            return None
