from __future__ import annotations

import sqlite3

from src.core.models.asset_class import AssetClass
from src.core.models.fund import FundInfo


class FundRepo:
    """
    基金信息仓储（SQLite）。

    职责：新增/更新基金、按代码读取、列出全部基金。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(self, fund_code: str, name: str, asset_class: AssetClass, market: str) -> None:  # type: ignore[override]
        """新增或更新基金信息（fund_code 幂等）。"""
        with self.conn:
            self.conn.execute(
                (
                    "INSERT INTO funds(fund_code, name, asset_class, market) VALUES(?, ?, ?, ?) "
                    "ON CONFLICT(fund_code) DO UPDATE SET name=excluded.name, "  # noqa: E501
                    "asset_class=excluded.asset_class, market=excluded.market"
                ),
                (fund_code, name, asset_class.value, market),
            )

    def get(self, fund_code: str) -> FundInfo | None:  # type: ignore[override]
        """按基金代码读取，未找到返回 None。"""
        row = self.conn.execute(
            "SELECT * FROM funds WHERE fund_code = ?",
            (fund_code,),
        ).fetchone()
        if not row:
            return None
        return _row_to_fund_info(row)

    def list_all(self) -> list[FundInfo]:  # type: ignore[override]
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


def _row_to_fund_info(row: sqlite3.Row) -> FundInfo:
    """将 SQLite Row 转换为 FundInfo 对象。"""
    return FundInfo(
        fund_code=row["fund_code"],
        name=row["name"],
        asset_class=AssetClass(row["asset_class"]),
        market=row["market"],
    )
