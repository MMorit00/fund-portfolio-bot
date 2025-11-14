from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict

from src.core.assets.classes import AssetClass
from src.core.portfolio.rebalance import calc_deviation, suggest_rebalance_amount
from src.usecases.ports import AllocConfigRepo, ReportSender, TradeRepo


@dataclass
class ReportData:
    total_value: Decimal
    class_value: Dict[AssetClass, Decimal]
    class_weight: Dict[AssetClass, Decimal]
    deviation: Dict[AssetClass, Decimal]


class GenerateDailyReport:
    """
    生成并发送日报（文本版）。
    MVP 简化：
    - 市值/权重计算依赖仓储提供的持仓与最新净值（可留后续实现）
    - 文本拼装尽量简洁
    """

    def __init__(self, alloc_repo: AllocConfigRepo, trade_repo: TradeRepo, sender: ReportSender) -> None:
        self.alloc_repo = alloc_repo
        self.trade_repo = trade_repo
        self.sender = sender

    def build(self) -> str:
        # TODO: 从仓储读取最新市值与权重（此处占位）
        text = []
        text.append("【持仓日报】\n")
        text.append("- 总市值：待实现\n")
        text.append("- 资产类别权重：待实现\n")
        text.append("- 再平衡提示：待实现\n")
        return "".join(text)

    def send(self) -> bool:
        return self.sender.send(self.build())

