from __future__ import annotations

from decimal import Decimal
from typing import Dict

from src.core.assets.classes import AssetClass


def calc_deviation(actual: Dict[AssetClass, Decimal], target: Dict[AssetClass, Decimal]) -> Dict[AssetClass, Decimal]:
    """
    计算每个资产类别的权重偏离（实际 - 目标）。
    所有权重使用 [0,1] 间的小数表示。
    """

    dev: Dict[AssetClass, Decimal] = {}
    for cls, tgt in target.items():
        a = actual.get(cls, Decimal("0"))
        dev[cls] = a - tgt
    return dev


def suggest_rebalance_amount(total_value: Decimal, deviation: Decimal) -> Decimal:
    """
    简化再平衡建议金额：取偏离的一半规模。
    仅作为提示用，非投资建议。
    """

    return (total_value * deviation.copy_abs()) / Decimal("2")

