from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.core.trade import Trade
from src.usecases.ports import FundRepo, TradeRepo


class CreateTrade:
    """
    创建一笔买入/卖出交易（pending）。

    注意：
    - 金额使用 Decimal
    - 日期默认今天（在入口层解析）
    - 市场类型从 FundRepo 读取
    """

    def __init__(self, trade_repo: TradeRepo, fund_repo: FundRepo) -> None:
        self.trade_repo = trade_repo
        self.fund_repo = fund_repo

    def execute(self, *, fund_code: str, trade_type: str, amount: Decimal, trade_day: date) -> Trade:
        fund = self.fund_repo.get_fund(fund_code)
        if not fund:
            raise ValueError(f"未知基金代码：{fund_code}")

        market = fund.get("market")
        if market not in ("A", "QDII"):
            raise ValueError("基金 market 配置无效，应为 'A' 或 'QDII'")

        trade = Trade(
            id=None,
            fund_code=fund_code,
            type=trade_type,  # 'buy' or 'sell'
            amount=amount,
            trade_date=trade_day,
            status="pending",
            market=market,
        )
        return self.trade_repo.add(trade)

