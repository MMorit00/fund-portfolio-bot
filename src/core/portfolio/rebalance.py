from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from src.core.asset_class import AssetClass


def calc_weight_difference(actual: dict[AssetClass, Decimal], target: dict[AssetClass, Decimal]) -> dict[AssetClass, Decimal]:
    """
    计算每个资产类别的权重差值（实际权重 - 目标权重）。

    用于再平衡分析：正值表示超配，负值表示低配。
    所有权重使用 [0,1] 间的小数表示。
    """

    dev: dict[AssetClass, Decimal] = {}
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


@dataclass(slots=True)
class RebalanceAdvice:
    """
    再平衡建议（按资产类别）。

    - action: "buy"=建议增持，"sell"=建议减持，"hold"=在阈值内观察；
    - amount: 建议调整金额（货币单位，非负），仅提示用；
    - weight_diff: 实际权重 - 目标权重（正=超配，负=低配）；
    - current_weight / target_weight / threshold: 当前/目标权重与生效阈值。
    """

    asset_class: AssetClass
    action: Literal["buy", "sell", "hold"]
    amount: Decimal
    weight_diff: Decimal
    current_weight: Decimal
    target_weight: Decimal
    threshold: Decimal


def build_rebalance_advice(
    total_value: Decimal,
    actual_weight: dict[AssetClass, Decimal],
    target_weight: dict[AssetClass, Decimal],
    thresholds: dict[AssetClass, Decimal] | None = None,
    default_threshold: Decimal = Decimal("0.05"),
) -> list[RebalanceAdvice]:
    """
    基于当前权重、目标权重与阈值，构造按资产类别的再平衡建议列表。

    - 仅依赖传入参数，不做 IO；
    - abs(diff) <= threshold 时 action="hold", amount=0；
    - abs(diff) > threshold 时：
        - amount = suggest_rebalance_amount(total_value, diff)（>=0）；
        - diff > 0 → "sell"（超配），diff < 0 → "buy"（低配）。
    - 返回列表按 abs(diff) 从大到小排序。
    """

    advices: list[RebalanceAdvice] = []
    for cls, tgt in target_weight.items():
        cur = actual_weight.get(cls, Decimal("0"))
        diff = cur - tgt
        th = (thresholds or {}).get(cls, default_threshold)

        if diff.copy_abs() <= th:
            advices.append(
                RebalanceAdvice(
                    asset_class=cls,
                    action="hold",
                    amount=Decimal("0"),
                    weight_diff=diff,
                    current_weight=cur,
                    target_weight=tgt,
                    threshold=th,
                )
            )
            continue

        amount = suggest_rebalance_amount(total_value, diff)
        action: Literal["buy", "sell"] = "sell" if diff > 0 else "buy"
        advices.append(
            RebalanceAdvice(
                asset_class=cls,
                action=action,
                amount=amount,
                weight_diff=diff,
                current_weight=cur,
                target_weight=tgt,
                threshold=th,
            )
        )

    advices.sort(key=lambda a: a.weight_diff.copy_abs(), reverse=True)
    return advices
