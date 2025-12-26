"""
计算类 AI 工具（纯函数）。

职责：
- 提供数学计算能力供 AI 调用
- 纯函数，不访问数据库
- 用于 AI 不擅长的精确计算

设计原则：
- 无副作用
- 输入输出类型明确
- 返回值可 JSON 序列化
"""

from __future__ import annotations

from typing import Any


def calc_execution_rate(expected: int, actual: int) -> dict[str, Any]:
    """
    计算定投执行率。

    Args:
        expected: 预期执行次数。
        actual: 实际执行次数。

    Returns:
        包含执行率和状态评估的字典。

    示例：
        result = calc_execution_rate(expected=4, actual=3)
        # {"expected": 4, "actual": 3, "rate": "75.0%", "status": "偏低"}
    """
    if expected == 0:
        return {"error": "预期次数不能为 0"}

    rate = actual / expected * 100
    if rate >= 90:
        status = "正常"
    elif rate >= 70:
        status = "偏低"
    else:
        status = "异常"

    return {
        "expected": expected,
        "actual": actual,
        "rate": f"{rate:.1f}%",
        "status": status,
    }


def calc_deviation_rate(expected_amount: str, actual_amount: str) -> dict[str, Any]:
    """
    计算金额偏差率。

    Args:
        expected_amount: 预期金额（字符串格式的 Decimal）。
        actual_amount: 实际金额（字符串格式的 Decimal）。

    Returns:
        包含偏差率和评估的字典。

    示例：
        result = calc_deviation_rate("100.00", "95.00")
        # {"expected": "100.00", "actual": "95.00", "deviation": "-5.00%", "status": "轻微偏差"}
    """
    from decimal import Decimal, InvalidOperation

    try:
        expected = Decimal(expected_amount)
        actual = Decimal(actual_amount)
    except InvalidOperation:
        return {"error": "金额格式无效"}

    if expected == 0:
        return {"error": "预期金额不能为 0"}

    deviation = (actual - expected) / expected * 100

    if abs(deviation) <= 5:
        status = "正常"
    elif abs(deviation) <= 20:
        status = "轻微偏差"
    else:
        status = "显著偏差"

    return {
        "expected": expected_amount,
        "actual": actual_amount,
        "deviation": f"{deviation:+.2f}%",
        "status": status,
    }


def format_amount(amount: str, decimals: int = 2) -> dict[str, Any]:
    """
    格式化金额显示。

    Args:
        amount: 金额字符串。
        decimals: 小数位数（默认 2）。

    Returns:
        格式化后的金额字符串。
    """
    from decimal import Decimal, InvalidOperation

    try:
        value = Decimal(amount)
        formatted = f"{value:,.{decimals}f}"
        return {"formatted": formatted, "original": amount}
    except InvalidOperation:
        return {"error": f"金额格式无效: {amount}"}
