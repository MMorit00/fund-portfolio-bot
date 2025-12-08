from __future__ import annotations

import argparse
import sys
from decimal import Decimal

from src.core.log import log
from src.flows.config import (
    add_dca_plan,
    delete_dca_plan,
    disable_dca_plan,
    enable_dca_plan,
    list_dca_plans,
)
from src.flows.dca_backfill import backfill_dca_for_batch, build_dca_facts_for_batch
from src.flows.dca_infer import draft_dca_plans


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli.dca_plan",
        description="定投计划管理（v0.3.2）",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="子命令")

    # ========== add 子命令 ==========
    add_parser = subparsers.add_parser("add", help="添加或更新定投计划")
    add_parser.add_argument("--fund", required=True, help="基金代码")
    add_parser.add_argument("--amount", required=True, type=Decimal, help="定投金额")
    add_parser.add_argument(
        "--freq",
        required=True,
        choices=["daily", "weekly", "monthly"],
        help="定投频率",
    )
    add_parser.add_argument(
        "--rule",
        required=True,
        help="定投规则（daily=空，weekly=MON/TUE/...，monthly=1..31）",
    )
    add_parser.add_argument(
        "--status",
        choices=["active", "disabled"],
        default="active",
        help="状态（默认 active）",
    )

    # ========== list 子命令 ==========
    list_parser = subparsers.add_parser("list", help="列出定投计划")
    list_parser.add_argument(
        "--active-only",
        action="store_true",
        help="仅显示活跃计划",
    )

    # ========== disable 子命令 ==========
    disable_parser = subparsers.add_parser("disable", help="禁用定投计划")
    disable_parser.add_argument("--fund", required=True, help="基金代码")

    # ========== enable 子命令 ==========
    enable_parser = subparsers.add_parser("enable", help="启用定投计划")
    enable_parser.add_argument("--fund", required=True, help="基金代码")

    # ========== delete 子命令 ==========
    delete_parser = subparsers.add_parser("delete", help="删除定投计划")
    delete_parser.add_argument("--fund", required=True, help="基金代码")

    # ========== infer 子命令 ==========
    infer_parser = subparsers.add_parser("infer", help="从历史买入记录推断定投计划候选")
    infer_parser.add_argument(
        "--min-samples",
        type=int,
        default=2,
        help="最小样本数（默认 2）",
    )
    infer_parser.add_argument(
        "--min-span-days",
        type=int,
        default=7,
        help="最小时间跨度（天，默认 7）",
    )
    infer_parser.add_argument(
        "--fund",
        type=str,
        default=None,
        help="只分析指定基金代码（默认分析所有基金）",
    )
    infer_parser.add_argument(
        "--batch-id",
        type=int,
        default=None,
        help="导入批次 ID（提供时输出事实快照供 AI 分析）",
    )

    # ========== backfill 子命令 ==========
    backfill_parser = subparsers.add_parser("backfill", help="回填历史导入交易的 DCA 归属")
    backfill_parser.add_argument(
        "--batch-id",
        type=int,
        required=True,
        help="导入批次 ID",
    )
    backfill_parser.add_argument(
        "--mode",
        choices=["dry-run", "apply"],
        default="dry-run",
        help="运行模式（默认 dry-run）",
    )
    backfill_parser.add_argument(
        "--fund",
        type=str,
        default=None,
        help="只回填指定基金代码（默认全部）",
    )

    return parser.parse_args()


def _do_add(args: argparse.Namespace) -> int:
    """执行 add 命令。"""
    try:
        # 1. 解析参数
        fund_code = args.fund
        amount = args.amount
        frequency = args.freq
        rule = args.rule
        status = args.status

        # 2. 添加定投计划
        log(f"[DCA:add] 添加定投计划：{fund_code} - {amount} 元/{frequency}/{rule} ({status})")
        add_dca_plan(
            fund_code=fund_code,
            amount=amount,
            frequency=frequency,
            rule=rule,
            status=status,
        )
        log(f"✅ 定投计划 {fund_code} 添加成功")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 添加定投计划失败：{err}")
        return 5


def _do_list(args: argparse.Namespace) -> int:
    """执行 list 命令。"""
    try:
        # 1. 查询定投计划
        active_only = args.active_only
        log(f"[DCA:list] 查询定投计划（active_only={active_only}）")
        plans = list_dca_plans(active_only=active_only)

        if not plans:
            log("（无定投计划）")
            return 0

        # 2. 格式化输出
        log(f"共 {len(plans)} 个定投计划：")
        for plan in plans:
            status_icon = "✅" if plan.status == "active" else "⏸️"
            log(
                f"  {status_icon} {plan.fund_code} | {plan.amount} 元/{plan.frequency}/{plan.rule} | {plan.status}"
            )
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 查询定投计划失败：{err}")
        return 5


def _do_disable(args: argparse.Namespace) -> int:
    """执行 disable 命令。"""
    try:
        # 1. 解析参数
        fund_code = args.fund

        # 2. 禁用定投计划
        log(f"[DCA:disable] 禁用定投计划：{fund_code}")
        disable_dca_plan(fund_code=fund_code)
        log(f"✅ 定投计划 {fund_code} 已禁用")
        return 0
    except ValueError as err:
        log(f"❌ 禁用失败：{err}")
        return 4
    except Exception as err:  # noqa: BLE001
        log(f"❌ 禁用定投计划失败：{err}")
        return 5


def _do_enable(args: argparse.Namespace) -> int:
    """执行 enable 命令。"""
    try:
        # 1. 解析参数
        fund_code = args.fund

        # 2. 启用定投计划
        log(f"[DCA:enable] 启用定投计划：{fund_code}")
        enable_dca_plan(fund_code=fund_code)
        log(f"✅ 定投计划 {fund_code} 已启用")
        return 0
    except ValueError as err:
        log(f"❌ 启用失败：{err}")
        return 4
    except Exception as err:  # noqa: BLE001
        log(f"❌ 启用定投计划失败：{err}")
        return 5


def _do_delete(args: argparse.Namespace) -> int:
    """执行 delete 命令。"""
    try:
        # 1. 解析参数
        fund_code = args.fund

        # 2. 删除定投计划
        log(f"[DCA:delete] 删除定投计划：{fund_code}")
        delete_dca_plan(fund_code=fund_code)
        log(f"✅ 定投计划 {fund_code} 已删除")
        return 0
    except ValueError as err:
        log(f"❌ 删除失败：{err}")
        return 4
    except Exception as err:  # noqa: BLE001
        log(f"❌ 删除定投计划失败：{err}")
        return 5


def _format_dca_facts(facts_list: list) -> None:  # noqa: ANN001
    """格式化输出 DCA 事实快照（供 AI 分析）。"""
    if not facts_list:
        log("（无事实快照）")
        return

    log(f"\n📊 DCA 事实快照（{len(facts_list)} 只基金）")
    log("=" * 60)

    for facts in facts_list:
        log(f"\n🔹 {facts.fund_code} ({facts.trade_count} 笔交易)")
        log(f"   时间范围: {facts.first_date} → {facts.last_date}")

        # 金额统计
        if facts.mode_amount is not None:
            log(f"   众数金额: {facts.mode_amount} 元")
        if facts.stable_count > 1 and facts.stable_amount is not None:
            log(f"   当前定投: {facts.stable_amount} 元（从 {facts.stable_since} 起，连续 {facts.stable_count} 笔）")

        # 间隔统计
        log(f"   众数间隔: {facts.mode_interval} 天")

        # 金额分布（优化显示）
        if len(facts.amount_histogram) > 1:
            log(f"   金额演变（{len(facts.amount_histogram)} 种）:")
            # 按金额降序显示（猜测是从高到低限额）
            sorted_amounts = sorted(
                facts.amount_histogram.items(),
                key=lambda x: -float(x[0])
            )
            for amt, count in sorted_amounts:
                pct = count / facts.trade_count * 100
                log(f"      • {amt} 元 × {count} 笔 ({pct:.1f}%)")
        elif facts.mode_amount:
            log(f"   金额稳定: {facts.mode_amount} 元（全部 {facts.trade_count} 笔）")

        # 间隔分布（简化显示）
        if len(facts.interval_histogram) <= 5:
            interval_str = ", ".join(f"{k}天:{v}" for k, v in sorted(facts.interval_histogram.items()))
            log(f"   间隔分布: {interval_str}")
        else:
            log(f"   间隔分布: {len(facts.interval_histogram)} 种不同间隔")

        # 特殊交易标记
        if facts.flags:
            log(f"   ⚠️ 特殊交易 ({len(facts.flags)} 笔):")
            for flag in facts.flags[:5]:
                log(f"      • trade_id={flag.trade_id} | {flag.trade_date} | {flag.amount} 元")
                log(f"        {flag.detail}")
            if len(facts.flags) > 5:
                log(f"      ... (还有 {len(facts.flags) - 5} 笔)")


def _do_infer(args: argparse.Namespace) -> int:
    """执行 infer 命令：从历史数据推断定投计划草案（draft_*() 规范）。"""
    try:
        # 1. 解析参数
        min_samples = args.min_samples
        min_span_days = args.min_span_days
        fund_code = args.fund
        batch_id = args.batch_id

        log(
            "[DCA:infer] 推断定投计划草案："
            f"min_samples={min_samples}, min_span_days={min_span_days}, fund={fund_code or 'ALL'}"
        )

        # 2. 如果提供了 batch-id，先输出事实快照（供 AI 分析）
        if batch_id is not None:
            log(f"\n[DCA:infer] 构建批次 {batch_id} 的事实快照...")
            facts_list = build_dca_facts_for_batch(batch_id=batch_id, fund_code=fund_code)
            _format_dca_facts(facts_list)
            log("\n" + "-" * 60)

        # 3. 调用推断 Flow（只读，返回草案 + 限额状态）
        result = draft_dca_plans(
            min_samples=min_samples,
            min_span_days=min_span_days,
            fund_code=fund_code,
        )

        # 4. 先输出当前限额状态（供 AI 分析）
        if result.fund_restrictions:
            log("\n📊 当前限额状态快照（供 AI 分析）：")
            log("=" * 80)
            for code in sorted(result.fund_restrictions.keys()):
                parsed = result.fund_restrictions[code]
                if parsed is None:
                    log(f"  {code} | 开放申购 | 无限制")
                else:
                    if parsed.restriction_type == "daily_limit":
                        log(
                            f"  {code} | 限购 {parsed.limit_amount} 元/日 "
                            f"| 置信度: {parsed.confidence}"
                        )
                    elif parsed.restriction_type == "suspend":
                        log(f"  {code} | 暂停申购 | 置信度: {parsed.confidence}")
                    elif parsed.restriction_type == "resume":
                        log(f"  {code} | 恢复申购 | 置信度: {parsed.confidence}")
            log("")

        # 5. 输出推断结果
        if not result.drafts:
            log("（未发现符合条件的定投模式）")
            return 0

        log(f"\n🎯 推断草案计划（{len(result.drafts)} 个）：")
        for d in result.drafts:
            icon = "⭐" if d.confidence == "high" else ("✨" if d.confidence == "medium" else "•")
            freq_rule = f"{d.frequency}/{d.rule}" if d.frequency != "daily" else "daily"
            log(
                f"  {icon} {d.fund_code} | {freq_rule} | 建议 {d.suggested_amount} 元 "
                f"| samples={d.sample_count}, span={d.span_days} 天, confidence={d.confidence} "
                f"| {d.first_date} → {d.last_date}"
            )

            # 变体数量提示
            if d.amount_variants > 1:
                log(f"      ⚠️  历史有 {d.amount_variants} 种金额，可能有演变")

            # 如果有限额，添加提示
            parsed = result.fund_restrictions.get(d.fund_code)
            if parsed and parsed.restriction_type == "daily_limit":
                if d.suggested_amount > parsed.limit_amount:
                    log(
                        f"      ⚠️  建议金额 {d.suggested_amount} 元超限额 {parsed.limit_amount} 元，"
                        f"请考虑调整"
                    )
                else:
                    log(f"      ✅ 符合当前限额 {parsed.limit_amount} 元/日")
            elif parsed and parsed.restriction_type == "suspend":
                log("      ⚠️  当前暂停申购，无法执行定投")

        log("\n提示：请根据以上结果，使用 `dca_plan add` 手动创建/调整正式定投计划。")
        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 推断定投计划失败：{err}")
        return 5


def _do_backfill(args: argparse.Namespace) -> int:
    """执行 backfill 命令：回填历史导入交易的 DCA 归属。"""
    try:
        # 1. 解析参数
        batch_id = args.batch_id
        mode = args.mode.replace("-", "_")  # "dry-run" → "dry_run"
        fund_code = args.fund

        log(
            f"[DCA:backfill] 回填 DCA 归属（{'干跑' if mode == 'dry_run' else '实际执行'}）："
            f"batch_id={batch_id}, fund={fund_code or 'ALL'}"
        )

        # 2. 调用回填 Flow
        result = backfill_dca_for_batch(
            batch_id=batch_id,
            mode=mode,
            fund_code=fund_code,
        )

        # 3. 格式化输出
        _format_backfill_result(result)

        return 0
    except Exception as err:  # noqa: BLE001
        log(f"❌ 回填 DCA 归属失败：{err}")
        return 5


def _format_backfill_result(result) -> None:  # noqa: ANN001
    """格式化回填结果输出。"""
    mode_label = "dry-run" if result.mode == "dry_run" else "apply"
    log(f"\n🔄 DCA 回填结果（{mode_label} 模式）")
    log(f"   Batch ID: {result.batch_id}")
    log(f"   基金范围: {result.fund_code_filter or '全部'}")
    log(f"   总交易数: {result.total_trades} 笔（仅 buy）")
    log(f"   匹配 DCA: {result.matched_count} 笔")
    log(f"   匹配率: {result.match_rate * 100:.1f}%")

    if result.mode == "apply":
        log(f"   已更新: {result.updated_count} 笔")

    # 按基金显示匹配详情
    if result.fund_summaries:
        log("\n📊 基金匹配详情:")
        for summary in result.fund_summaries:
            icon = "✅" if summary.has_dca_plan else "❌"
            log(f"   {icon} {summary.fund_code} ({summary.total_trades} 笔交易)")

            if summary.has_dca_plan:
                log(f"      定投计划: {summary.dca_plan_info}")
                log(f"      匹配结果: {summary.matched_trades}/{summary.total_trades} 笔")

                # dry-run 模式显示详细匹配原因（仅显示前5笔）
                if result.mode == "dry_run" and summary.matches:
                    log("      样例:")
                    for match in summary.matches[:5]:
                        match_icon = "✓" if match.matched else "✗"
                        log(
                            f"        {match_icon} {match.trade_date}: {match.amount} 元 - {match.match_reason}"
                        )
                    if len(summary.matches) > 5:
                        log(f"        ... (还有 {len(summary.matches) - 5} 笔)")
            else:
                log("      ❌ 无定投计划（跳过）")

    # 提示信息
    if result.mode == "dry_run":
        log("\n提示：使用 --mode apply 执行实际回填")
    else:
        log("\n✅ 回填完成")


def main() -> int:
    """
    定投计划管理 CLI（v0.4.3）。

    Returns:
        退出码：0=成功；4=计划不存在；5=其他失败。
    """
    # 1. 解析参数
    args = _parse_args()

    # 2. 路由到子命令
    if args.command == "add":
        return _do_add(args)
    elif args.command == "list":
        return _do_list(args)
    elif args.command == "disable":
        return _do_disable(args)
    elif args.command == "enable":
        return _do_enable(args)
    elif args.command == "delete":
        return _do_delete(args)
    elif args.command == "infer":
        return _do_infer(args)
    elif args.command == "backfill":
        return _do_backfill(args)
    else:
        log(f"❌ 未知命令：{args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
