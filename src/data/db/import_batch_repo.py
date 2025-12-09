from __future__ import annotations

import sqlite3
from datetime import datetime

from src.core.models.importer import ImportBatch


class ImportBatchRepo:
    """
    导入批次仓储（v0.4.3 新增）。

    职责：
    - 创建导入批次记录（create）；
    - 按 ID 查询批次（get）；
    - 支持历史导入的撤销和追溯。

    设计说明：
    - 每次历史导入（mode='apply'）时创建一条 batch 记录；
    - batch_id 关联到 trades.import_batch_id，用于后续回填和撤销；
    - 手动/自动交易不创建 batch（import_batch_id = NULL）。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(self, source: str, note: str | None = None) -> int:
        """
        创建导入批次记录。

        Args:
            source: 来源平台（'alipay' / 'ttjj'）。
            note: 可选备注（如文件路径）。

        Returns:
            新创建的 batch_id。

        副作用:
            向 import_batches 表插入一条记录。
        """
        created_at = datetime.now().isoformat(timespec="seconds")
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO import_batches (source, created_at, note) VALUES (?, ?, ?)",
                (source, created_at, note),
            )
            batch_id = cursor.lastrowid or 0
        return int(batch_id)

    def get(self, batch_id: int) -> ImportBatch | None:
        """
        按 ID 查询批次记录。

        Args:
            batch_id: 批次 ID。

        Returns:
            ImportBatch 对象，未找到返回 None。
        """
        row = self.conn.execute(
            "SELECT * FROM import_batches WHERE id = ?",
            (batch_id,),
        ).fetchone()
        if not row:
            return None
        return _row_to_batch(row)


def _row_to_batch(row: sqlite3.Row) -> ImportBatch:
    """将 SQLite Row 转换为 ImportBatch 对象。"""
    return ImportBatch(
        id=int(row["id"]),
        source=row["source"],
        created_at=datetime.fromisoformat(row["created_at"]),
        note=row["note"],
    )
