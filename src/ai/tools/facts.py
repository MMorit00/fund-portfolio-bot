"""
事实类 AI 工具（查库）。

职责：
- 提供数据查询能力供 AI 调用
- 返回结构化数据（dict）
- 包含数据截断保护

设计原则：
- 只读查询，不修改数据
- 返回值必须可 JSON 序列化
- 大数据集必须截断（MAX_ROWS）
- ActionLog 是核心信息源，LEFT JOIN Trade 补充成交数据
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from src.ai.registry import tool
from src.ai.schemas.arguments import ActionArgs, NavArgs, RestrictionArgs
from src.core.container import (
    get_action_repo,
    get_fund_restriction_repo,
    get_nav_repo,
    get_trade_repo,
)

logger = logging.getLogger(__name__)

# 数据行数限制，防止上下文溢出
MAX_ROWS = 50


@tool(NavArgs)
def get_nav(
    fund_code: str,
    query_date: str | None = None,
) -> dict[str, Any]:
    """
    查询基金净值。

    返回指定日期的净值，如未指定则返回最新可用数据。
    """
    logger.info(f"[AITools] get_nav: {fund_code}, date={query_date}")

    nav_repo = get_nav_repo()
    target = date.fromisoformat(query_date) if query_date else date.today()

    nav = nav_repo.get(fund_code, target)

    if nav is None:
        # 往前找最近的净值（最多 7 天）
        for i in range(1, 8):
            check = target - timedelta(days=i)
            nav = nav_repo.get(fund_code, check)
            if nav is not None:
                return {
                    "code": fund_code,
                    "nav": str(nav),
                    "date": check.isoformat(),
                    "note": f"未找到 {target} 的净值，返回最近数据",
                }

        return {"error": f"未找到 {fund_code} 近 7 天的净值"}

    return {
        "code": fund_code,
        "nav": str(nav),
        "date": target.isoformat(),
    }


@tool(ActionArgs)
def get_action(
    fund_code: str,
    period: str = "1m",
) -> dict[str, Any]:
    """
    查询投资行为流水。

    从 ActionLog 获取行为记录，LEFT JOIN Trade 补充成交数据。
    返回事件列表和汇总统计。
    """
    logger.info(f"[AITools] get_action: {fund_code}, period={period}")

    action_repo = get_action_repo()
    trade_repo = get_trade_repo()

    # 计算日期范围
    end = date.today()
    days_map = {"1m": 30, "3m": 90, "6m": 180, "ytd": (end - date(end.year, 1, 1)).days}
    days = days_map.get(period, 30)
    start = end - timedelta(days=days)

    # 1. 从 ActionLog 获取行为记录
    actions = action_repo.list_buy_actions(days=days)
    fund_actions = [a for a in actions if a.fund_code == fund_code][:MAX_ROWS]

    if not fund_actions:
        return {
            "code": fund_code,
            "period": f"{start.isoformat()} ~ {end.isoformat()}",
            "events": [],
            "stats": {"total": 0, "dca": 0, "amount": "0"},
        }

    # 2. LEFT JOIN Trade 补充成交数据
    trade_ids = [a.trade_id for a in fund_actions if a.trade_id]
    trades = trade_repo.list_by_ids(trade_ids) if trade_ids else []
    trade_map = {t.id: t for t in trades}

    # 3. 构建事件列表
    events: list[dict[str, Any]] = []
    total_amount = Decimal("0")
    dca_count = 0

    for action in fund_actions:
        event: dict[str, Any] = {
            "date": action.target_date.isoformat() if action.target_date else action.acted_at.date().isoformat(),
            "action": action.action,
            "strategy": action.strategy,
        }

        # 补充 Trade 数据
        if action.trade_id and action.trade_id in trade_map:
            trade = trade_map[action.trade_id]
            event["amount"] = str(trade.amount)
            event["shares"] = str(trade.shares) if trade.shares else None
            total_amount += trade.amount

        # 补充 note（如有）
        if action.note:
            event["note"] = action.note

        if action.strategy == "dca":
            dca_count += 1

        events.append(event)

    result: dict[str, Any] = {
        "code": fund_code,
        "period": f"{start.isoformat()} ~ {end.isoformat()}",
        "events": events,
        "stats": {
            "total": len(events),
            "dca": dca_count,
            "amount": str(total_amount),
        },
    }

    if len(fund_actions) == MAX_ROWS:
        result["warning"] = f"数据已截断，仅显示最近 {MAX_ROWS} 条"

    return result


@tool(RestrictionArgs)
def get_restriction(
    fund_code: str,
    query_date: str | None = None,
) -> dict[str, Any]:
    """
    查询基金限购/暂停信息。

    返回指定日期有效的限制记录。
    """
    logger.info(f"[AITools] get_restriction: {fund_code}, date={query_date}")

    repo = get_fund_restriction_repo()
    target = date.fromisoformat(query_date) if query_date else date.today()

    restrictions = repo.list_active_on(fund_code, target)

    if not restrictions:
        return {
            "code": fund_code,
            "date": target.isoformat(),
            "has_restriction": False,
        }

    # 取最新的限制
    latest = restrictions[0]

    return {
        "code": fund_code,
        "date": target.isoformat(),
        "has_restriction": True,
        "type": latest.restriction_type,
        "limit": str(latest.limit_amount) if latest.limit_amount else None,
        "start": latest.start_date.isoformat(),
        "end": latest.end_date.isoformat() if latest.end_date else None,
        "source": latest.source,
        "note": latest.note,
    }
