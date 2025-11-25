"""NAV 相关领域模型。"""

from enum import Enum


class NavQuality(Enum):
    """
    NAV 数据质量等级。

    - exact: 当日交易日 NAV（最佳质量）
    - holiday: 周末/节假日，使用最近交易日 NAV（正常降级）
    - delayed: NAV 延迟 1-2 天（可接受降级，需警告）
    - missing: 持续缺失 3+ 天（数据质量太差，跳过）
    """

    exact = "exact"
    holiday = "holiday"
    delayed = "delayed"
    missing = "missing"
