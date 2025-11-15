from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional

from src.core.asset_class import AssetClass
from src.usecases.ports import FundRepo


def _row_to_dict(row: sqlite3.Row) -> Dict:
    return {
        "fund_code": row["fund_code"],
        "name": row["name"],
        "asset_class": AssetClass(row["asset_class"]),
        "market": row["market"],
    }


class SqliteFundRepo(FundRepo):
    """基金信息仓储。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add_fund(self, fund_code: str, name: str, asset_class: AssetClass, market: str) -> None:  # type: ignore[override]
        with self.conn:
            self.conn.execute(
                (
                    "INSERT INTO funds(fund_code, name, asset_class, market) VALUES(?, ?, ?, ?) "
                    "ON CONFLICT(fund_code) DO UPDATE SET name=excluded.name, asset_class=excluded.asset_class, market=excluded.market"
                ),
                (fund_code, name, asset_class.value, market),
            )

    def get_fund(self, fund_code: str) -> Optional[Dict]:  # type: ignore[override]
        row = self.conn.execute(
            "SELECT * FROM funds WHERE fund_code = ?",
            (fund_code,),
        ).fetchone()
        if not row:
            return None
        return _row_to_dict(row)

    def list_funds(self) -> List[Dict]:  # type: ignore[override]
        rows = self.conn.execute("SELECT * FROM funds ORDER BY fund_code").fetchall()
        return [_row_to_dict(r) for r in rows]

