from __future__ import annotations

import sqlite3
from datetime import date, datetime

from src.core.models.action import ActionLog, ActionType


class ActionRepo:
    """
    行为日志仓储。

    负责 action_log 表的增查操作。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(self, log: ActionLog) -> ActionLog:
        """新增一条行为日志。"""
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO action_log (
                    action,
                    actor,
                    source,
                    acted_at,
                    fund_code,
                    target_date,
                    trade_id,
                    intent,
                    note,
                    strategy
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log.action,
                    log.actor,
                    log.source,
                    log.acted_at.strftime("%Y-%m-%d %H:%M:%S"),  # SQLite datetime 兼容格式
                    log.fund_code,
                    log.target_date.isoformat() if log.target_date else None,
                    log.trade_id,
                    log.intent,
                    log.note,
                    log.strategy,
                ),
            )
            log_id = cursor.lastrowid or 0
        return ActionLog(
            id=int(log_id),
            action=log.action,
            actor=log.actor,
            source=log.source,
            acted_at=log.acted_at,
            fund_code=log.fund_code,
            target_date=log.target_date,
            trade_id=log.trade_id,
            intent=log.intent,
            note=log.note,
            strategy=log.strategy,
        )

    def list_by_action(self, action: ActionType) -> list[ActionLog]:
        """按动作类型查询日志。"""
        rows = self.conn.execute(
            "SELECT * FROM action_log WHERE action = ? ORDER BY acted_at DESC",
            (action,),
        ).fetchall()
        return [_row_to_action_log(r) for r in rows]

    def list_by_trade(self, trade_id: int) -> list[ActionLog]:
        """按交易 ID 查询日志。"""
        rows = self.conn.execute(
            "SELECT * FROM action_log WHERE trade_id = ? ORDER BY acted_at DESC",
            (trade_id,),
        ).fetchall()
        return [_row_to_action_log(r) for r in rows]

    def list_recent(self, days: int = 30) -> list[ActionLog]:
        """查询最近 N 天的日志。"""
        rows = self.conn.execute(
            """
            SELECT * FROM action_log
            WHERE acted_at >= datetime('now', '-' || ? || ' days')
            ORDER BY acted_at DESC
            """,
            (days,),
        ).fetchall()
        return [_row_to_action_log(r) for r in rows]

    def list_buy_actions(self, days: int | None = None) -> list[ActionLog]:
        """
        查询用于 DCA 推断的买入行为日志。

        仅包含：
        - action = 'buy'
        - source in ('manual', 'import')
        """
        if days is not None:
            rows = self.conn.execute(
                """
                SELECT * FROM action_log
                WHERE action = 'buy'
                  AND source IN ('manual', 'import')
                  AND acted_at >= datetime('now', '-' || ? || ' days')
                ORDER BY acted_at DESC
                """,
                (days,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT * FROM action_log
                WHERE action = 'buy'
                  AND source IN ('manual', 'import')
                ORDER BY acted_at DESC
                """
            ).fetchall()
        return [_row_to_action_log(r) for r in rows]

    def update_strategy_by_trade_ids(self, trade_ids: list[int], strategy: str) -> int:
        """
        批量更新 action_log.strategy 字段（v0.4.3 DCA 回填使用）。

        Args:
            trade_ids: 交易 ID 列表。
            strategy: 策略标签（如 "dca"）。

        Returns:
            实际更新的行数。
        """
        if not trade_ids:
            return 0
        placeholders = ",".join("?" for _ in trade_ids)
        with self.conn:
            cursor = self.conn.execute(
                f"UPDATE action_log SET strategy = ? WHERE trade_id IN ({placeholders})",
                [strategy, *trade_ids],
            )
        return cursor.rowcount


def _row_to_action_log(row: sqlite3.Row) -> ActionLog:
    """将 action_log 表的 SQLite 行记录转换为 ActionLog 实体。"""
    target_date_str = row["target_date"]
    acted_at_str = row["acted_at"]

    return ActionLog(
        id=int(row["id"]),
        action=row["action"],
        actor=row["actor"],
        source=row["source"],
        acted_at=datetime.fromisoformat(acted_at_str),
        fund_code=row["fund_code"],
        target_date=date.fromisoformat(target_date_str) if target_date_str else None,
        trade_id=int(row["trade_id"]) if row["trade_id"] is not None else None,
        intent=row["intent"],
        note=row["note"],
        strategy=row["strategy"],
    )
