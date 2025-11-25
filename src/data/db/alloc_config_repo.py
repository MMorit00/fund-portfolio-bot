from __future__ import annotations

import sqlite3
from decimal import Decimal

from src.core.models.alloc_config import AllocConfig
from src.core.models.asset_class import AssetClass


class AllocConfigRepo:
    """资产配置目标权重仓储（SQLite）。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _load_decimal_map(self, column: str) -> dict[AssetClass, Decimal]:
        if column not in {"target_weight", "max_deviation"}:
            raise ValueError("invalid column")
        rows = self.conn.execute(
            f"SELECT asset_class, {column} FROM alloc_config"
        ).fetchall()
        data: dict[AssetClass, Decimal] = {}
        for row in rows:
            asset_class = AssetClass(row["asset_class"])
            data[asset_class] = Decimal(row[column])
        return data

    def get_target_weights(self) -> dict[AssetClass, Decimal]:  # type: ignore[override]
        """返回资产类别目标权重（0..1）。"""
        return self._load_decimal_map("target_weight")

    def get_max_deviation(self) -> dict[AssetClass, Decimal]:  # type: ignore[override]
        """返回各资产类别允许的最大偏离（0..1）。"""
        return self._load_decimal_map("max_deviation")

    def set_alloc(
        self,
        asset_class: AssetClass,
        target_weight: Decimal,
        max_deviation: Decimal,
    ) -> None:
        """
        设置资产配置目标（v0.3.2 新增）。

        Args:
            asset_class: 资产类别。
            target_weight: 目标权重（0..1）。
            max_deviation: 允许的最大偏离（0..1）。

        副作用：
            按 (asset_class) 幂等插入或更新 alloc_config 表。
        """
        self.conn.execute(
            """
            INSERT INTO alloc_config (asset_class, target_weight, max_deviation)
            VALUES (?, ?, ?)
            ON CONFLICT(asset_class) DO UPDATE SET
                target_weight = excluded.target_weight,
                max_deviation = excluded.max_deviation
            """,
            (asset_class.value, str(target_weight), str(max_deviation)),
        )
        self.conn.commit()

    def list_all(self) -> list[AllocConfig]:
        """
        查询所有资产配置目标（v0.3.2 新增）。

        Returns:
            所有资产配置列表，按 asset_class 排序。
        """
        rows = self.conn.execute(
            "SELECT * FROM alloc_config ORDER BY asset_class"
        ).fetchall()
        return [_row_to_config(r) for r in rows]

    def delete(self, asset_class: AssetClass) -> None:
        """
        删除资产配置目标（v0.3.4 新增）。

        Args:
            asset_class: 资产类别。

        Raises:
            ValueError: 配置不存在时抛出。

        副作用：
            从 alloc_config 表删除指定资产配置。
        """
        cursor = self.conn.execute(
            "DELETE FROM alloc_config WHERE asset_class = ?",
            (asset_class.value,),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"资产配置不存在：{asset_class.value}")
        self.conn.commit()


def _row_to_config(row: sqlite3.Row) -> AllocConfig:
    """将 SQLite Row 转换为 AllocConfig 对象。"""
    return AllocConfig(
        asset_class=AssetClass(row["asset_class"]),
        target_weight=Decimal(row["target_weight"]),
        max_deviation=Decimal(row["max_deviation"]),
    )
