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
        """
        创建一笔 pending 交易，并写入数据库（由仓储预写确认日）。

        Args:
            fund_code: 基金代码，需已存在于 funds 表。
            trade_type: 交易类型，`buy` 或 `sell`。
            amount: 金额，必须大于 0（Decimal）。
            trade_day: 交易日期（下单/约定日）。

        Returns:
            入库后的 Trade 实体（包含生成的 id）。

        可能抛出：
            - ValueError: 基金不存在或 market 配置无效。
        """
        fund = self.fund_repo.get_fund(fund_code)
        if not fund:
            raise ValueError(f"未知基金代码：{fund_code}")

        trade = Trade(
            id=None,
            fund_code=fund_code,
            type=trade_type,  # 'buy' or 'sell'
            amount=amount,
            trade_date=trade_day,
            status="pending",
            market=fund.market,
        )
        return self.trade_repo.add(trade)
