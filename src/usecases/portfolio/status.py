from __future__ import annotations

from src.core.protocols import TradeRepo


class GetStatusSummary:
    """
    获取组合简要状态概览（总市值、各类权重等）。
    MVP 简化：由仓储计算或提供聚合视图（后续实现）。
    """

    def __init__(self, trade_repo: TradeRepo) -> None:
        self.trade_repo = trade_repo

    def execute(self) -> dict[str, str]:
        # TODO: 返回总市值/分类权重等（占位）
        return {"message": "状态摘要：待实现"}

