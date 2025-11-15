from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal
from typing import Optional

from src.usecases.ports import NavRepo


class SqliteNavRepo(NavRepo):
    """SQLite NAV 仓储。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert(self, fund_code: str, day: date, nav: Decimal) -> None:  # type: ignore[override]
        with self.conn:
            self.conn.execute(
                (
                    "INSERT INTO navs(fund_code, day, nav) VALUES(?, ?, ?) "
                    "ON CONFLICT(fund_code, day) DO UPDATE SET nav=excluded.nav"
                ),
                (fund_code, day.isoformat(), format(nav, "f")),
            )

    def get(self, fund_code: str, day: date) -> Optional[Decimal]:  # type: ignore[override]
        row = self.conn.execute(
            "SELECT nav FROM navs WHERE fund_code = ? AND day = ?",
            (fund_code, day.isoformat()),
        ).fetchone()
        if not row:
            return None
        return Decimal(row["nav"])

