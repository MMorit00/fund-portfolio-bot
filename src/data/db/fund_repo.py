from __future__ import annotations

import sqlite3

from src.core.models.asset_class import AssetClass
from src.core.models.fund import Fund
from src.core.models.trade import MarketType


class FundRepo:
    """
    基金信息仓储（SQLite）。

    职责：新增/更新基金、按代码读取、列出全部基金。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(
        self,
        fund_code: str,
        name: str,
        asset_class: AssetClass,
        market: MarketType,
        external_name: str | None = None,
    ) -> None:
        """新增或更新基金信息（fund_code 幂等）。"""
        with self.conn:
            self.conn.execute(
                (
                    "INSERT INTO funds(fund_code, name, asset_class, market, alias) "
                    "VALUES(?, ?, ?, ?, ?) "
                    "ON CONFLICT(fund_code) DO UPDATE SET name=excluded.name, "
                    "asset_class=excluded.asset_class, market=excluded.market, "
                    "alias=excluded.alias"
                ),
                (fund_code, name, asset_class, market, external_name),
            )

    def get(self, fund_code: str) -> Fund | None:
        """按基金代码读取，未找到返回 None。"""
        row = self.conn.execute(
            "SELECT * FROM funds WHERE fund_code = ?",
            (fund_code,),
        ).fetchone()
        if not row:
            return None
        return _row_to_fund_info(row)

    def list_all(self) -> list[Fund]:
        """按 fund_code 排序返回全部基金。"""
        rows = self.conn.execute("SELECT * FROM funds ORDER BY fund_code").fetchall()
        return [_row_to_fund_info(r) for r in rows]

    def delete(self, fund_code: str) -> None:
        """
        删除基金（v0.3.4 新增）。

        Args:
            fund_code: 基金代码。

        Raises:
            ValueError: 基金不存在时抛出。

        副作用：
            从 funds 表删除指定基金。
        """
        cursor = self.conn.execute(
            "DELETE FROM funds WHERE fund_code = ?",
            (fund_code,),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"基金不存在：{fund_code}")
        self.conn.commit()

    def find_by_external_name(self, external_name: str) -> Fund | None:
        """
        通过外部完整名称查找基金。

        用于历史账单导入时，根据平台完整基金名称查找对应的 fund_code。
        注意：当前仍使用 funds.alias 字段存储该外部名称。
        TODO: 将来考虑引入独立的 FundNameMapping 表，替代直接使用 funds.alias。

        Args:
            external_name: 平台完整基金名称（精确匹配）。

        Returns:
            匹配的 Fund，未找到返回 None。
        """
        row = self.conn.execute(
            "SELECT * FROM funds WHERE alias = ?",
            (external_name,),
        ).fetchone()
        if not row:
            return None
        return _row_to_fund_info(row)

    def update_external_name(self, fund_code: str, external_name: str | None) -> None:
        """
        更新基金的外部名称。

        注意：当前仍映射到 funds.alias 字段。
        TODO: 与 find_by_external_name 一并迁移到独立映射表后，收敛此方法。

        Args:
            fund_code: 基金代码。
            external_name: 平台完整基金名称，None 表示清除。

        Raises:
            ValueError: 基金不存在时抛出。
        """
        cursor = self.conn.execute(
            "UPDATE funds SET alias = ? WHERE fund_code = ?",
            (external_name, fund_code),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"基金不存在：{fund_code}")
        self.conn.commit()

def _row_to_fund_info(row: sqlite3.Row) -> Fund:
    """将 SQLite Row 转换为 Fund 对象。"""
    return Fund(
        fund_code=row["fund_code"],
        name=row["name"],
        asset_class=AssetClass(row["asset_class"]),
        market=MarketType(row["market"]),
        external_name=row["alias"],
    )
