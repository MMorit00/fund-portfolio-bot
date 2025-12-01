"""导入账单市值验证 CLI（v0.4.2+）"""

from __future__ import annotations

import argparse
from datetime import date

from src.core.log import log
from src.flows.import_verify import verify_import_market_value


def main() -> None:
    """验证导入账单后的市值计算。"""
    parser = argparse.ArgumentParser(description="导入账单市值验证")
    parser.add_argument("--as-of", type=str, help="查询日期（YYYY-MM-DD）")
    parser.add_argument("--estimate", action="store_true", help="使用估值回退")
    args = parser.parse_args()

    # 解析日期
    as_of: date | None = None
    if args.as_of:
        try:
            as_of = date.fromisoformat(args.as_of)
        except ValueError:
            print(f"❌ 日期格式错误：{args.as_of}，正确格式：YYYY-MM-DD")
            return

    log(f"[VerifyImport] 查询日期: {as_of or '上一交易日'}, 估值: {args.estimate}")
    result = verify_import_market_value(as_of=as_of, use_estimate=args.estimate)

    # 输出
    print(f"\n📊 导入账单市值验证（{result.as_of}）\n")
    print(f"总市值: ¥{result.total_market_value:,.2f}")
    print(f"待确认: ¥{result.pending_amount:,.2f}\n")

    # 统计
    print("数据来源统计:")
    print(f"  - 官方净值: {result.official_nav_count} 只基金")
    if result.estimated_nav_count > 0:
        print(f"  - 估值顶替: {result.estimated_nav_count} 只基金")
    if result.missing_nav_count > 0:
        print(f"  - 净值缺失: {result.missing_nav_count} 只基金 ⚠️")
    print()

    # 明细
    if result.holdings:
        print("基金明细:\n")
        for h in result.holdings:
            nav_str = f"{h.nav:.4f} [{h.nav_source}]" if h.nav else "N/A"
            mv_str = f"¥{h.market_value:,.2f}" if h.market_value else "N/A"
            print(f"  {h.fund_name} ({h.fund_code})")
            print(f"    份额: {h.shares:,.2f}  净值: {nav_str}  市值: {mv_str}")
            if h.estimated_time:
                print(f"    估值时间: {h.estimated_time}")
            print()
    else:
        print("暂无持仓\n")

    # 说明
    if result.estimated_nav_count > 0:
        print("说明: [估] 表示盘中估值，仅供参考\n")
    if result.missing_nav_count > 0:
        print(f"⚠️  {result.missing_nav_count} 只基金净值缺失，建议运行 fetch_navs\n")


if __name__ == "__main__":
    main()
