"""基金费率仓储（v0.4.4 新增）。

设计说明：
- 表层（fund_fee_items）：通用的"条目"模型，支持多种 fee_type 和阶梯
- 域层（FundFees）：聚合视图，隐藏表结构细节，面向业务使用
- 当前实现：通过 get_fees() 把表行组装为 FundFees 对象

TODO（未来演进方向）：
- 如需新增 fee_type，只需在此文件的枚举和 get_fees() 的 if 分支中增加即可
- 如需暴露"单条费率记录"给业务层，可新增：
    @dataclass
    class FundFeeItem:
        fund_code: str
        fee_type: str
        charge_basis: str
        rate: Decimal
        min_hold_days: int | None
        max_hold_days: int | None
  并提供 get_fee_items(fund_code) -> list[FundFeeItem] 方法
- 如需按 charge_basis 做统计，可直接查表或通过新增方法实现
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from src.core.models.fund import FundFees, RedemptionFeeTier

# fee_type 枚举值
fee_type_management = "management"
fee_type_custody = "custody"
fee_type_service = "service"
fee_type_purchase = "purchase"
fee_type_purchase_discount = "purchase_discount"
fee_type_redemption = "redemption"

# charge_basis 枚举值
charge_basis_annual = "annual"
charge_basis_transaction = "transaction"


class FundFeeRepo:
    """
    基金费率仓储（SQLite）。

    职责：读写 fund_fee_items 表，提供 FundFees 聚合视图。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get_fees(self, fund_code: str) -> FundFees | None:
        """
        获取基金费率（聚合视图）。

        Args:
            fund_code: 基金代码。

        Returns:
            FundFees 对象，若无任何费率记录则返回 None。
        """
        rows = self.conn.execute(
            "SELECT fee_type, rate, min_hold_days, max_hold_days "
            "FROM fund_fee_items WHERE fund_code = ?",
            (fund_code,),
        ).fetchall()

        if not rows:
            return None

        fees = FundFees()
        redemption_tiers: list[RedemptionFeeTier] = []

        for row in rows:
            fee_type = row["fee_type"]
            rate = Decimal(row["rate"])

            if fee_type == fee_type_management:
                fees.management_fee = rate
            elif fee_type == fee_type_custody:
                fees.custody_fee = rate
            elif fee_type == fee_type_service:
                fees.service_fee = rate
            elif fee_type == fee_type_purchase:
                fees.purchase_fee = rate
            elif fee_type == fee_type_purchase_discount:
                fees.purchase_fee_discount = rate
            elif fee_type == fee_type_redemption:
                tier = RedemptionFeeTier(
                    min_hold_days=row["min_hold_days"] or 0,
                    max_hold_days=row["max_hold_days"],
                    rate=rate,
                )
                redemption_tiers.append(tier)

        # 按 min_hold_days 升序排列
        redemption_tiers.sort(key=lambda t: t.min_hold_days)
        fees.redemption_tiers = redemption_tiers

        return fees

    def upsert_fees(self, fund_code: str, fees: FundFees) -> None:
        """
        写入/更新基金费率（全量替换）。

        Args:
            fund_code: 基金代码。
            fees: FundFees 对象。

        副作用：
            先删除该基金的所有费率记录，再写入新记录。
        """
        with self.conn:
            # 先删除旧记录
            self.conn.execute(
                "DELETE FROM fund_fee_items WHERE fund_code = ?",
                (fund_code,),
            )

            # 写入运作费率
            if fees.management_fee is not None:
                self._insert_fee(
                    fund_code,
                    fee_type_management,
                    charge_basis_annual,
                    fees.management_fee,
                )
            if fees.custody_fee is not None:
                self._insert_fee(
                    fund_code,
                    fee_type_custody,
                    charge_basis_annual,
                    fees.custody_fee,
                )
            if fees.service_fee is not None:
                self._insert_fee(
                    fund_code,
                    fee_type_service,
                    charge_basis_annual,
                    fees.service_fee,
                )

            # 写入申购费率
            if fees.purchase_fee is not None:
                self._insert_fee(
                    fund_code,
                    fee_type_purchase,
                    charge_basis_transaction,
                    fees.purchase_fee,
                )
            if fees.purchase_fee_discount is not None:
                self._insert_fee(
                    fund_code,
                    fee_type_purchase_discount,
                    charge_basis_transaction,
                    fees.purchase_fee_discount,
                )

            # 写入赎回费阶梯
            for tier in fees.redemption_tiers:
                self._insert_redemption_tier(fund_code, tier)

    def has_operating_fees(self, fund_code: str) -> bool:
        """
        检查是否已有运作费率（管理费或托管费）。

        用于 skip_if_exists 判断。

        Args:
            fund_code: 基金代码。

        Returns:
            True 如果已有管理费或托管费记录。
        """
        row = self.conn.execute(
            "SELECT 1 FROM fund_fee_items "
            "WHERE fund_code = ? AND fee_type IN (?, ?) LIMIT 1",
            (fund_code, fee_type_management, fee_type_custody),
        ).fetchone()
        return row is not None

    def get_redemption_fee(self, fund_code: str, hold_days: int) -> Decimal | None:
        """
        获取指定持有天数的赎回费率。

        Args:
            fund_code: 基金代码。
            hold_days: 持有天数。

        Returns:
            匹配的赎回费率，未找到返回 None。
        """
        # 查找满足 min_hold_days <= hold_days < max_hold_days 的记录
        # max_hold_days 为 NULL 表示无上限
        row = self.conn.execute(
            """
            SELECT rate FROM fund_fee_items
            WHERE fund_code = ? AND fee_type = ?
              AND min_hold_days <= ?
              AND (max_hold_days IS NULL OR max_hold_days > ?)
            ORDER BY min_hold_days DESC LIMIT 1
            """,
            (fund_code, fee_type_redemption, hold_days, hold_days),
        ).fetchone()

        if row:
            return Decimal(row["rate"])
        return None

    def _insert_fee(
        self,
        fund_code: str,
        fee_type: str,
        charge_basis: str,
        rate: Decimal,
        min_hold_days: int | None = None,
        max_hold_days: int | None = None,
    ) -> None:
        """插入单条费率记录。"""
        self.conn.execute(
            """
            INSERT INTO fund_fee_items
            (fund_code, fee_type, charge_basis, rate, min_hold_days, max_hold_days)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (fund_code, fee_type, charge_basis, str(rate), min_hold_days, max_hold_days),
        )

    def _insert_redemption_tier(
        self, fund_code: str, tier: RedemptionFeeTier
    ) -> None:
        """插入赎回费阶梯记录。"""
        self._insert_fee(
            fund_code,
            fee_type_redemption,
            charge_basis_transaction,
            tier.rate,
            tier.min_hold_days,
            tier.max_hold_days,
        )
