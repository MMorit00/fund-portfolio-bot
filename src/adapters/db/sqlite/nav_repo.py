from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from src.usecases.ports import NavRepo


class SqliteNavRepo(NavRepo):
    """SQLite 实现（占位）。"""

    def __init__(self) -> None:
        pass

    def upsert(self, fund_code: str, day: date, nav: Decimal) -> None:  # type: ignore[override]
        raise NotImplementedError

    def get(self, fund_code: str, day: date) -> Optional[Decimal]:  # type: ignore[override]
        raise NotImplementedError

