from __future__ import annotations

from decimal import Decimal
from typing import Dict

from src.core.asset_class import AssetClass


def calc_weight_difference(actual: Dict[AssetClass, Decimal], target: Dict[AssetClass, Decimal]) -> Dict[AssetClass, Decimal]:
    """
    计算每个资产类别的权重差值（实际权重 - 目标权重）。

    用于再平衡分析：正值表示超配，负值表示低配。
    所有权重使用 [0,1] 间的小数表示。
    """

    dev: Dict[AssetClass, Decimal] = {}
    for cls, tgt in target.items():
        a = actual.get(cls, Decimal("0"))
        dev[cls] = a - tgt
    return dev


def suggest_rebalance_amount(total_value: Decimal, weight_diff: Decimal) -> Decimal:
    """
    基于权重差值给出渐进式再平衡金额建议。

    口径：建议金额 = 总市值 × |权重差值| × 50%；仅用于提示，非投资建议。
    """

    return (total_value * weight_diff.copy_abs()) / Decimal("2")
