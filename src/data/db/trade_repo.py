from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from src.core.models.trade import MarketType, Trade
from src.core.rules.precision import quantize_amount
from src.core.rules.settlement import calc_settlement_dates, default_policy
from src.data.db.calendar import CalendarService


class TradeRepo:
    """
    SQLite 交易仓储实现。

    负责按当前确认规则在创建交易时预写 `confirm_date`，并提供：
    - 待确认交易查询；
    - 确认更新（写入份额与确认用 NAV）；
    - 已确认持仓份额聚合。
    """

    def __init__(self, conn: sqlite3.Connection, calendar: CalendarService) -> None:
        self.conn = conn
        self.calendar = calendar

    def add(self, trade: Trade) -> Trade:
        """新增一条交易记录（v16：支持 fee/apply_amount/apply_shares）。"""
        normalized_amount = quantize_amount(trade.amount)
        policy = default_policy(trade.market)
        pricing_day, confirm_day = calc_settlement_dates(trade.trade_date, policy, self.calendar)
        with self.conn:
            cursor = self.conn.execute(
                (
                    "INSERT INTO trades (fund_code, type, amount, trade_date, status, market, "
                    "shares, remark, pricing_date, confirm_date, confirmation_status, "
                    "delayed_reason, delayed_since, external_id, import_batch_id, dca_plan_key, "
                    "fee, apply_amount, apply_shares) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                (
                    trade.fund_code,
                    trade.type,
                    format(normalized_amount, "f"),
                    trade.trade_date.isoformat(),
                    trade.status,
                    trade.market,
                    _decimal_to_str(trade.shares),
                    trade.remark,
                    pricing_day.isoformat(),
                    confirm_day.isoformat(),
                    trade.confirmation_status,
                    trade.delayed_reason,
                    trade.delayed_since.isoformat() if trade.delayed_since else None,
                    trade.external_id,
                    trade.import_batch_id,
                    trade.dca_plan_key,
                    _decimal_to_str(trade.fee),
                    _decimal_to_str(trade.apply_amount),
                    _decimal_to_str(trade.apply_shares),
                ),
            )
            trade_id = cursor.lastrowid or 0
        return Trade(
            id=int(trade_id),
            fund_code=trade.fund_code,
            type=trade.type,
            amount=normalized_amount,
            trade_date=trade.trade_date,
            status=trade.status,
            market=trade.market,
            shares=trade.shares,
            remark=trade.remark,
            pricing_date=pricing_day,
            confirm_date=confirm_day,
            confirmation_status=trade.confirmation_status,
            delayed_reason=trade.delayed_reason,
            delayed_since=trade.delayed_since,
            external_id=trade.external_id,
            import_batch_id=trade.import_batch_id,
            dca_plan_key=trade.dca_plan_key,
            fee=trade.fee,
            apply_amount=trade.apply_amount,
            apply_shares=trade.apply_shares,
        )

    def list_pending(self, confirm_date: date) -> list[Trade]:
        """
        查询待确认交易（包括过期交易以支持延迟追踪）。

        返回所有 confirm_date <= 指定日期 的 pending 交易，按 id 升序。
        """
        rows = self.conn.execute(
            "SELECT * FROM trades WHERE status = ? AND confirm_date <= ? ORDER BY id",
            ("pending", confirm_date.isoformat()),
        ).fetchall()
        return [_row_to_trade(r) for r in rows]

    def confirm(self, trade_id: int, shares: Decimal) -> None:
        """
        将指定交易标记为已确认，写入份额（v0.2.1：重置延迟标记）。

        注意：nav 归一化存储于 navs 表，confirm 不需要 nav 参数。
        """
        with self.conn:
            self.conn.execute(
                """
                UPDATE trades SET
                    status = ?,
                    shares = ?,
                    confirmation_status = 'normal',
                    delayed_reason = NULL,
                    delayed_since = NULL
                WHERE id = ?
                """,
                (
                    "confirmed",
                    _decimal_to_str(shares),
                    trade_id,
                ),
            )

    def update(self, trade: Trade) -> None:
        """更新交易记录（v0.2.1：支持延迟追踪字段更新）。"""
        with self.conn:
            self.conn.execute(
                """
                UPDATE trades SET
                    status = ?,
                    shares = ?,
                    confirmation_status = ?,
                    delayed_reason = ?,
                    delayed_since = ?
                WHERE id = ?
                """,
                (
                    trade.status,
                    _decimal_to_str(trade.shares),
                    trade.confirmation_status,
                    trade.delayed_reason,
                    trade.delayed_since.isoformat() if trade.delayed_since else None,
                    trade.id,
                ),
            )

    def list_recent_trades(self, days: int = 7) -> list[Trade]:
        """列出最近 N 天的交易（v0.2.1：用于日报展示）。"""
        rows = self.conn.execute(
            """
            SELECT * FROM trades
            WHERE trade_date >= date('now', '-' || ? || ' days')
            ORDER BY trade_date DESC, id DESC
            """,
            (days,),
        ).fetchall()
        return [_row_to_trade(r) for r in rows]

    def list_by_status(self, status: str) -> list[Trade]:
        """
        按状态查询交易（v0.3.2 新增）。

        Args:
            status: 交易状态（pending/confirmed/skipped）。

        Returns:
            符合条件的交易列表，按 trade_date 降序、id 降序排列。
        """
        rows = self.conn.execute(
            "SELECT * FROM trades WHERE status = ? ORDER BY trade_date DESC, id DESC",
            (status,),
        ).fetchall()
        return [_row_to_trade(r) for r in rows]

    def get_position(self, up_to: date | None = None) -> dict[str, Decimal]:
        """
        按基金代码聚合已确认交易，返回净持仓份额。

        Args:
            up_to: 截止日期，None 表示全部。

        Returns:
            {fund_code: shares} 字典，仅包含正持仓。
        """
        if up_to:
            rows = self.conn.execute(
                """SELECT fund_code, type, shares FROM trades
                   WHERE status = 'confirmed' AND shares IS NOT NULL AND trade_date <= ?""",
                (up_to.isoformat(),),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT fund_code, type, shares FROM trades WHERE status = 'confirmed' AND shares IS NOT NULL"
            ).fetchall()
        position: dict[str, Decimal] = {}
        for row in rows:
            shares = Decimal(row["shares"])
            if row["type"] == "sell":
                shares = -shares
            position[row["fund_code"]] = position.get(row["fund_code"], Decimal("0")) + shares
        return {k: v for k, v in position.items() if v > 0}

    def get_pending_amount(self, up_to: date | None = None) -> Decimal:
        """
        统计待确认买入金额。

        Args:
            up_to: 截止日期，None 表示全部。

        Returns:
            待确认金额总和。
        """
        if up_to:
            row = self.conn.execute(
                """SELECT SUM(amount) as total FROM trades
                   WHERE status = 'pending' AND type = 'buy' AND trade_date <= ?""",
                (up_to.isoformat(),),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT SUM(amount) as total FROM trades WHERE status = 'pending' AND type = 'buy'"
            ).fetchone()
        total = row["total"] if row and row["total"] is not None else "0"
        return Decimal(str(total))

    def skip_dca_for_date(self, fund_code: str, day: date) -> int:
        """将指定日期的 pending 买入定投标记为 skipped，返回影响行数。"""
        cur = self.conn.execute(
            """
            UPDATE trades
            SET status = 'skipped'
            WHERE fund_code = ?
              AND type = 'buy'
              AND status = 'pending'
              AND trade_date = ?
            """,
            (fund_code, day.isoformat()),
        )
        self.conn.commit()
        return cur.rowcount

    def list_delayed_trades(self, days: int = 30) -> list[Trade]:
        """
        列出最近 N 天内的延迟交易（v0.3.2 新增）。

        Args:
            days: 查询天数范围，默认 30 天。

        Returns:
            confirmation_status='delayed' 的交易列表，按 trade_date 降序排列。
        """
        rows = self.conn.execute(
            """
            SELECT * FROM trades
            WHERE confirmation_status = 'delayed'
              AND trade_date >= date('now', '-' || ? || ' days')
            ORDER BY trade_date DESC, id DESC
            """,
            (days,),
        ).fetchall()
        return [_row_to_trade(r) for r in rows]

    def cancel(self, trade_id: int) -> None:
        """
        取消 pending 交易（v0.3.4 新增）。

        Args:
            trade_id: 交易 ID。

        Raises:
            ValueError: 交易不存在或不是 pending 状态时抛出。

        副作用：
            将 status 从 pending 更新为 skipped。
        """
        cursor = self.conn.execute(
            "UPDATE trades SET status = 'skipped' WHERE id = ? AND status = 'pending'",
            (trade_id,),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"交易不存在或不可取消（仅支持 pending 状态）：trade_id={trade_id}")
        self.conn.commit()

    def exists_by_external_id(self, external_id: str) -> bool:
        """
        检查指定 external_id 是否已存在（v0.4.2 新增）。

        Args:
            external_id: 外部唯一标识。

        Returns:
            True 表示已存在，False 表示不存在。
        """
        row = self.conn.execute(
            "SELECT 1 FROM trades WHERE external_id = ? LIMIT 1",
            (external_id,),
        ).fetchone()
        return row is not None

    def list_by_ids(self, trade_ids: list[int]) -> list[Trade]:
        """
        按 ID 列表批量查询交易记录（用于分析场景，如 DCA 推断）。

        Args:
            trade_ids: 交易主键 ID 列表（可包含重复值）。

        Returns:
            对应的 Trade 列表，顺序按 id 升序。
        """
        if not trade_ids:
            return []
        unique_ids = sorted(set(trade_ids))
        placeholders = ",".join("?" for _ in unique_ids)
        rows = self.conn.execute(
            f"SELECT * FROM trades WHERE id IN ({placeholders}) ORDER BY id",
            unique_ids,
        ).fetchall()
        return [_row_to_trade(r) for r in rows]

    def list_by_batch(self, batch_id: int, fund_code: str | None = None) -> list[Trade]:
        """
        查询指定批次的交易（v0.4.3 DCA 回填使用）。

        Args:
            batch_id: 导入批次 ID。
            fund_code: 可选的基金代码过滤（None=全部）。

        Returns:
            交易列表，按 fund_code, trade_date 升序排列。
        """
        if fund_code is not None:
            rows = self.conn.execute(
                """
                SELECT * FROM trades
                WHERE import_batch_id = ? AND fund_code = ?
                ORDER BY fund_code, trade_date
                """,
                (batch_id, fund_code),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT * FROM trades
                WHERE import_batch_id = ?
                ORDER BY fund_code, trade_date
                """,
                (batch_id,),
            ).fetchall()
        return [_row_to_trade(r) for r in rows]

    def update_dca_plan_key_bulk(self, trade_ids: list[int], dca_plan_key: str | None) -> int:
        """
        批量更新交易的 dca_plan_key 字段（v0.4.3 DCA 回填使用）。

        Args:
            trade_ids: 交易 ID 列表。
            dca_plan_key: DCA 计划标识（当前格式=fund_code），None 表示清除。

        Returns:
            实际更新的行数。
        """
        if not trade_ids:
            return 0
        placeholders = ",".join("?" for _ in trade_ids)
        with self.conn:
            cursor = self.conn.execute(
                f"UPDATE trades SET dca_plan_key = ? WHERE id IN ({placeholders})",
                [dca_plan_key, *trade_ids],
            )
        return cursor.rowcount

    def get(self, trade_id: int) -> Trade | None:
        """
        获取单笔交易（v0.4.5 新增）。

        Args:
            trade_id: 交易 ID。

        Returns:
            Trade 对象，不存在则返回 None。
        """
        row = self.conn.execute(
            "SELECT * FROM trades WHERE id = ?",
            (trade_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_trade(row)

    def list_ids_by_fund_and_date(self, fund_code: str, trade_date: date) -> list[int]:
        """
        获取同一天同基金的交易 ID 列表（v0.4.5 新增，用于 set_dca_core）。

        Args:
            fund_code: 基金代码。
            trade_date: 交易日期。

        Returns:
            交易 ID 列表。
        """
        rows = self.conn.execute(
            "SELECT id FROM trades WHERE fund_code = ? AND trade_date = ?",
            (fund_code, trade_date.isoformat()),
        ).fetchall()
        return [row["id"] for row in rows]


def _decimal_to_str(value: Decimal | None) -> str | None:
    """将 Decimal 转换为字符串格式，None 原样返回。"""
    if value is None:
        return None
    return format(value, "f")


def _row_to_trade(row: sqlite3.Row) -> Trade:
    """将 trades 表的 SQLite 行记录转换为 Trade 实体（v16：支持 fee/apply_amount/apply_shares）。"""
    shares = row["shares"]
    confirm_date_str = row["confirm_date"]
    delayed_since_str = row["delayed_since"]
    keys = row.keys()

    return Trade(
        id=int(row["id"]),
        fund_code=row["fund_code"],
        type=row["type"],
        amount=Decimal(row["amount"]),
        trade_date=date.fromisoformat(row["trade_date"]),
        status=row["status"],
        market=MarketType(row["market"]),
        shares=Decimal(shares) if shares is not None else None,
        remark=row["remark"],
        pricing_date=date.fromisoformat(row["pricing_date"]) if row["pricing_date"] else None,
        confirm_date=date.fromisoformat(confirm_date_str) if confirm_date_str else None,
        confirmation_status=row["confirmation_status"] or "normal",
        delayed_reason=row["delayed_reason"],
        delayed_since=date.fromisoformat(delayed_since_str) if delayed_since_str else None,
        external_id=row["external_id"],
        import_batch_id=row["import_batch_id"] if "import_batch_id" in keys else None,
        dca_plan_key=row["dca_plan_key"] if "dca_plan_key" in keys else None,
        fee=Decimal(row["fee"]) if "fee" in keys and row["fee"] else None,
        apply_amount=Decimal(row["apply_amount"]) if "apply_amount" in keys and row["apply_amount"] else None,
        apply_shares=Decimal(row["apply_shares"]) if "apply_shares" in keys and row["apply_shares"] else None,
    )
