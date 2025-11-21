from __future__ import annotations

from enum import Enum


class AssetClass(str, Enum):
    """
    资产类别枚举（可扩展）。

    - CSI300: A股宽基（沪深300）
    - US_QDII: 美股 QDII 基金
    - CGB_3_5Y: 中短债（3-5Y）
    """

    CSI300 = "CSI300"
    US_QDII = "US_QDII"
    CGB_3_5Y = "CGB_3_5Y"

