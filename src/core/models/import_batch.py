"""导入批次数据模型。

用途：
- ImportBatch: 导入批次记录，用于追溯和撤销。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

# 导入来源
ImportSource = Literal["alipay", "ttjj", "alipay_pdf"]


@dataclass(slots=True)
class ImportBatch:
    """导入批次记录。

    用途：
    - 作为"撤销点"和"追溯源"，确保每次历史导入都有明确边界；
    - 支持批次级别的撤销、重跑、查询（WHERE import_batch_id = ?）；
    - 手动/自动交易不关联批次（import_batch_id = NULL）。

    生命周期：
    - 在 import 开始时创建；
    - 返回的 batch_id 传递给后续 Trade 写入流程；
    - 写入 import_batches 表后不再修改。
    """

    source: str
    """来源平台（alipay / ttjj / alipay_pdf）。"""

    created_at: datetime
    """创建时间（ISO 格式）。"""

    id: int | None = None
    """批次 ID（写入数据库后自动生成）。"""

    note: str | None = None
    """可选备注（用于记录导入文件路径等）。"""
