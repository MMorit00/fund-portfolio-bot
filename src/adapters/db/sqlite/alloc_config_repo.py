from __future__ import annotations

import sqlite3
from decimal import Decimal
from typing import Dict

from src.core.asset_class import AssetClass
from src.usecases.ports import AllocConfigRepo


class SqliteAllocConfigRepo(AllocConfigRepo):
    """资产配置目标权重仓储（SQLite）。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _load_decimal_map(self, column: str) -> Dict[AssetClass, Decimal]:
        if column not in {"target_weight", "max_deviation"}:
            raise ValueError("invalid column")
        rows = self.conn.execute(
            f"SELECT asset_class, {column} FROM alloc_config"
        ).fetchall()
        data: Dict[AssetClass, Decimal] = {}
        for row in rows:
            asset_class = AssetClass(row["asset_class"])
            data[asset_class] = Decimal(row[column])
        return data

    def get_target_weights(self) -> Dict[AssetClass, Decimal]:  # type: ignore[override]
        """返回资产类别目标权重（0..1）。"""
        return self._load_decimal_map("target_weight")

    def get_max_deviation(self) -> Dict[AssetClass, Decimal]:  # type: ignore[override]
        """返回各资产类别允许的最大偏离（0..1）。"""
        return self._load_decimal_map("max_deviation")
