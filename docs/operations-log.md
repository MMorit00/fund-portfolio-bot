# 运维快速参考

> 快速查阅。命令详情见 `--help`，详细说明见 `docs/history-import.md`。

## 日常流程

```bash
# 早上 9:00 执行（按顺序）
uv run python -m src.cli.dca                # 1. 执行定投
uv run python -m src.cli.fetch_navs         # 2. 抓取净值
uv run python -m src.cli.confirm            # 3. 确认交易
uv run python -m src.cli.report             # 4. 生成日报
```

## 常用命令

**基金管理**
```bash
uv run python -m src.cli.fund add --code 000001 --name "华夏成长" --class CSI300 --market CN_A
uv run python -m src.cli.fund list
uv run python -m src.cli.fund remove --code 000001
```

**定投计划**
```bash
uv run python -m src.cli.dca_plan add --fund 000001 --amount 1000 --freq monthly --rule 1
uv run python -m src.cli.dca_plan list
uv run python -m src.cli.dca_plan backfill --batch-id 3 --mode dry-run
uv run python -m src.cli.dca_plan backfill --batch-id 3 --mode apply
```

**交易**
```bash
uv run python -m src.cli.trade buy --fund 000001 --amount 5000
uv run python -m src.cli.trade sell --fund 000001 --shares 100
uv run python -m src.cli.trade list --status pending
uv run python -m src.cli.trade confirm --id 123
uv run python -m src.cli.trade cancel --id 123
```

**历史导入**
```bash
uv run python -m src.cli.history_import --csv data/alipay.csv --mode dry-run
uv run python -m src.cli.history_import --csv data/alipay.csv --mode apply

# 导入后查看 DCA 事实快照
uv run python -m src.cli.dca_facts batch <batch_id>             # 批次概览
uv run python -m src.cli.dca_facts fund <batch_id> <fund_code>  # 单基金详情
```

**限额管理**
```bash
uv run python -m src.cli.fund_restriction check-status --fund 016532
uv run python -m src.cli.fund_restriction check-status --fund 016532 --apply
uv run python -m src.cli.fund_restriction add --fund 008971 --type daily_limit --start 2025-11-01 --limit 10
uv run python -m src.cli.fund_restriction end --fund 008971 --type daily_limit --date 2025-12-31
```

**数据报告**
```bash
uv run python -m src.cli.fetch_navs --date 2025-12-08
uv run python -m src.cli.report --date 2025-12-08
uv run python -m src.cli.rebalance
uv run python -m src.cli.market_value
```

**日历**
```bash
uv run python -m src.cli.calendar sync --market CN_A --from 2020-01-01 --to 2025-12-31
uv run python -m src.cli.calendar patch-cn-a --back 30 --forward 365
```

## 环境变量

```bash
export DB_PATH=data/portfolio.db           # 数据库路径（默认）
export DISCORD_WEBHOOK_URL=https://...     # Discord Webhook
export ENABLE_SQL_DEBUG=1                  # SQL 日志
```

## 故障排查

| 问题 | 解决 |
|------|------|
| NAV 缺失 | `uv run python -m src.cli.fetch_navs --date YYYY-MM-DD` |
| 交易延迟 | `uv run python -m src.cli.trade confirm-manual --id ID --shares X --nav Y` |
| 数据库损坏 | `rm data/portfolio.db && SEED_RESET=1 PYTHONPATH=. python -m scripts.dev_seed_db` |

## 进阶说明

- **DCA 推断/回填**：见 `docs/history-import.md`
- **限额功能**：见 `docs/history-import.md`
- **交易确认规则**：见 `docs/settlement-rules.md`
- **数据库架构**：见 `docs/sql-schema.md`
