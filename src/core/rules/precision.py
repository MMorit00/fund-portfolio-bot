"""
金额/份额/NAV 精度工具函数。

统一精度规则：
- 金额：2 位小数（人民币/美元最小单位为分/美分）
- 份额：4 位小数（基金份额通常精确到万分位）
- NAV：4 位小数（基金净值通常为 4 位小数）
"""

from decimal import ROUND_HALF_UP, Decimal


def quantize_amount(amount: Decimal) -> Decimal:
    """
    将金额量化为 2 位小数。

    Args:
        amount: 金额（Decimal）。

    Returns:
        量化后的金额（2 位小数）。
    """
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def quantize_shares(shares: Decimal) -> Decimal:
    """
    将份额量化为 4 位小数。

    Args:
        shares: 份额（Decimal）。

    Returns:
        量化后的份额（4 位小数）。
    """
    return shares.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def quantize_nav(nav: Decimal) -> Decimal:
    """
    将净值量化为 4 位小数。

    Args:
        nav: 净值（Decimal）。

    Returns:
        量化后的净值（4 位小数）。
    """
    return nav.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
