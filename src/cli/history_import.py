"""历史账单导入 CLI。

v0.4.2 新增：支持从支付宝等平台导入历史基金交易。
详细设计见 docs/history-import.md

用法：
    # 干跑：检查 CSV 是否有问题
    python -m src.cli.history_import --csv data/alipay.csv --mode dry-run

    # 实际导入
    python -m src.cli.history_import --csv data/alipay.csv --mode apply

    # 禁用 ActionLog 记录
    python -m src.cli.history_import --csv data/alipay.csv --mode apply --no-actions

当前状态：骨架实现，调用 Flow 时会提示未实现。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.flows.history_import import import_trades_from_csv


def main() -> None:
    """历史账单导入 CLI 入口。"""
    parser = argparse.ArgumentParser(
        description="从支付宝等平台导入历史基金交易记录",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 干跑模式（只检查，不写入）
  python -m src.cli.history_import --csv data/alipay.csv --mode dry-run

  # 实际导入
  python -m src.cli.history_import --csv data/alipay.csv --mode apply

详细设计见 docs/history-import.md
""",
    )

    parser.add_argument(
        "--csv",
        required=True,
        help="CSV 文件路径（支付宝账单导出）",
    )
    parser.add_argument(
        "--mode",
        choices=["dry-run", "apply"],
        default="dry-run",
        help="导入模式：dry-run=只检查（默认），apply=实际写入",
    )
    parser.add_argument(
        "--source",
        choices=["alipay", "ttjj"],
        default="alipay",
        help="来源平台（默认 alipay）",
    )
    parser.add_argument(
        "--no-actions",
        action="store_true",
        help="禁用 ActionLog 记录",
    )

    args = parser.parse_args()

    # 检查文件是否存在
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"错误：文件不存在 {csv_path}")
        sys.exit(1)

    # 转换参数
    mode = "dry_run" if args.mode == "dry-run" else "apply"
    with_actions = not args.no_actions

    print(f"📥 历史账单导入（{args.mode} 模式）")
    print(f"   CSV 文件: {csv_path}")
    print(f"   来源平台: {args.source}")
    print(f"   记录行为: {'是' if with_actions else '否'}")
    print()

    try:
        result = import_trades_from_csv(
            csv_path=str(csv_path),
            source=args.source,
            mode=mode,
            with_actions=with_actions,
        )

        # 输出结果（dry-run 用"可导入"，apply 用"成功"）
        if mode == "dry_run":
            print("✅ 检查完成")
            print(f"   总计: {result.total} 笔")
            print(f"   可导入: {result.succeeded} 笔")
            print(f"   失败: {result.failed} 笔")
            print(f"   跳过: {result.skipped} 笔")
        else:
            print("✅ 导入完成")
            print(f"   总计: {result.total} 笔")
            print(f"   成功: {result.succeeded} 笔")
            print(f"   失败: {result.failed} 笔")
            print(f"   跳过: {result.skipped} 笔")
            print(f"   成功率: {result.success_rate:.1%}")

        if result.failed_records:
            print()
            print("❌ 失败记录:")
            for record in result.failed_records[:10]:
                print(
                    f"   [{record.error_type}] {record.original_fund_name}: "
                    f"{record.error_message}"
                )
            if len(result.failed_records) > 10:
                print(f"   ... 还有 {len(result.failed_records) - 10} 条")

    except NotImplementedError as e:
        print(f"⚠️  {e}")
        print()
        print("提示：历史导入功能正在开发中，当前只完成了接口设计。")
        sys.exit(0)


if __name__ == "__main__":
    main()
