"""账单 CSV 解析器。

支持支付宝基金 PDF 导出的 CSV 格式（UTF-8-SIG）。
"""

from __future__ import annotations

import csv
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from src.core.models.bill import (
    TRADE_TYPE_MAP,
    BillErrorCode,
    BillItem,
    BillParseError,
    BillTradeType,
)

# CSV 列名映射
CSV_COLUMNS = [
    "订单号",
    "交易时间",
    "交易类型",
    "基金名称",
    "组合基金名称",
    "基金代码",
    "申请金额",
    "申请份额",
    "确认金额",
    "确认份额",
    "手续费",
    "确认日期",
]


def _clean_order_id(raw: str) -> str:
    """清理订单号（去除空格）。"""
    return raw.replace(" ", "")


def _clean_fund_name(raw: str) -> str:
    """清理基金名称（去除换行符和多余空格）。"""
    # 替换各种空白字符为单个空格，然后去除首尾空白
    return re.sub(r"\s+", " ", raw).strip()


def _parse_decimal(raw: str) -> Decimal | None:
    """解析金额（不经过 float）。"""
    if not raw or raw == "/":
        return None
    try:
        return Decimal(raw.strip())
    except InvalidOperation:
        return None


def _parse_trade_time(raw: str) -> datetime | None:
    """解析交易时间（格式：2025/12/08 10:12）。"""
    try:
        return datetime.strptime(raw.strip(), "%Y/%m/%d %H:%M")
    except ValueError:
        return None


def _parse_confirm_date(raw: str) -> date | None:
    """解析确认日期（格式：2025/12/10 00:00）。"""
    try:
        # 确认日期带时间但我们只需要日期部分
        dt = datetime.strptime(raw.strip(), "%Y/%m/%d %H:%M")
        return dt.date()
    except ValueError:
        return None


def _parse_trade_type(raw: str) -> BillTradeType | None:
    """解析交易类型。"""
    return TRADE_TYPE_MAP.get(raw.strip())


def parse_bill_csv(path: Path | str) -> tuple[list[BillItem], list[BillParseError]]:
    """解析支付宝基金 PDF 导出的 CSV 文件。

    Args:
        path: CSV 文件路径

    Returns:
        (items, errors): 解析成功的记录和解析错误列表
    """
    path = Path(path)
    items: list[BillItem] = []
    errors: list[BillParseError] = []

    # 读取文件（UTF-8-SIG 处理 BOM）
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row_num, row in enumerate(reader, start=2):  # 从第2行开始（第1行是表头）
            try:
                item, error = _parse_row(row_num, row)
                if item:
                    items.append(item)
                if error:
                    errors.append(error)
            except Exception as e:
                # 捕获未预期的异常
                errors.append(
                    BillParseError(
                        row_num=row_num,
                        error_type=BillErrorCode.ROW_PARSE_ERROR,
                        raw_data=str(row),
                        message=f"未预期的解析错误: {e}",
                    )
                )

    return items, errors


def _parse_row(
    row_num: int, row: dict[str, str]
) -> tuple[BillItem | None, BillParseError | None]:
    """解析单行 CSV 数据。

    Returns:
        (item, error): 解析成功的记录（可能为 None）和解析错误（可能为 None）
    """
    # 解析交易类型
    trade_type_raw = row.get("交易类型", "")
    trade_type = _parse_trade_type(trade_type_raw)
    if not trade_type:
        return None, BillParseError(
            row_num=row_num,
            error_type=BillErrorCode.UNKNOWN_TRADE_TYPE,
            raw_data=str(row),
            message=f"未知交易类型: {trade_type_raw}",
        )

    # 解析基金代码
    fund_code = row.get("基金代码", "").strip()
    # 清理可能的注释文本（取第一个空格前的部分）
    fund_code = fund_code.split()[0] if fund_code else ""
    if not fund_code:
        return None, BillParseError(
            row_num=row_num,
            error_type=BillErrorCode.MISSING_FUND_CODE,
            raw_data=str(row),
            message="缺少基金代码",
        )

    # 解析交易时间
    trade_time = _parse_trade_time(row.get("交易时间", ""))
    if not trade_time:
        return None, BillParseError(
            row_num=row_num,
            error_type=BillErrorCode.INVALID_DATE,
            raw_data=str(row),
            message=f"交易时间解析失败: {row.get('交易时间', '')}",
        )

    # 解析确认日期
    confirm_date = _parse_confirm_date(row.get("确认日期", ""))
    if not confirm_date:
        return None, BillParseError(
            row_num=row_num,
            error_type=BillErrorCode.INVALID_DATE,
            raw_data=str(row),
            message=f"确认日期解析失败: {row.get('确认日期', '')}",
        )

    # 解析金额
    apply_amount = _parse_decimal(row.get("申请金额", ""))
    confirm_amount = _parse_decimal(row.get("确认金额", ""))
    confirm_shares = _parse_decimal(row.get("确认份额", ""))
    fee = _parse_decimal(row.get("手续费", ""))

    # 金额校验
    if apply_amount is None:
        return None, BillParseError(
            row_num=row_num,
            error_type=BillErrorCode.INVALID_AMOUNT,
            raw_data=str(row),
            message=f"申请金额解析失败: {row.get('申请金额', '')}",
        )
    if confirm_amount is None:
        return None, BillParseError(
            row_num=row_num,
            error_type=BillErrorCode.INVALID_AMOUNT,
            raw_data=str(row),
            message=f"确认金额解析失败: {row.get('确认金额', '')}",
        )
    if confirm_shares is None:
        return None, BillParseError(
            row_num=row_num,
            error_type=BillErrorCode.INVALID_AMOUNT,
            raw_data=str(row),
            message=f"确认份额解析失败: {row.get('确认份额', '')}",
        )
    if fee is None:
        # 手续费可能为空，默认 0
        fee = Decimal("0")

    # 构建 BillItem
    item = BillItem(
        order_id=_clean_order_id(row.get("订单号", "")),
        trade_time=trade_time,
        trade_type=trade_type,
        fund_name=_clean_fund_name(row.get("基金名称", "")),
        fund_code=fund_code,
        apply_amount=apply_amount,
        confirm_amount=confirm_amount,
        confirm_shares=confirm_shares,
        fee=fee,
        confirm_date=confirm_date,
    )

    return item, None
