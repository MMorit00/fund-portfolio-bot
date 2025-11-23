from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.core.models.asset_class import AssetClass


@dataclass(slots=True)
class AllocConfig:
    """
    资产配置目标（v0.3.2 新增）。

    - target_weight: 目标权重（0..1）
    - max_deviation: 允许的最大偏离（0..1）
    """

    asset_class: AssetClass
    target_weight: Decimal
    max_deviation: Decimal
