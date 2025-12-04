# 运维手册

> 当前版本操作命令与配置方式

## 快速开始

```bash
# 安装依赖
uv sync

# 初始化数据库（首次使用）
rm data/portfolio.db
SEED_RESET=1 PYTHONPATH=. python -m scripts.dev_seed_db

# 日常流程（早上 9:00）
python -m src.cli.dca              # 执行定投
python -m src.cli.fetch_navs       # 抓取昨日 NAV
python -m src.cli.confirm          # 确认交易
python -m src.cli.report           # 生成日报
```

## CLI 命令速查

| 分类 | 命令 | 说明 |
|------|------|------|
| **配置** | `fund add/list/remove` | 基金管理 |
| | `dca_plan add/list/enable/disable/delete/infer` | 定投计划 |
| | `alloc set/show` | 资产配置 |
| **交易** | `trade buy/sell` | 手动交易 |
| | `trade list/cancel/confirm-manual` | 交易管理 |
| | `dca run/skip` | 定投执行 |
| **数据** | `fetch_navs/range` | 净值抓取 |
| | `report/rebalance/market_value` | 报告查询 |
| | `action list` | 行为日志 |
| **日历** | `calendar sync/patch-cn-a` | 日历管理 |

## 常用配置

```bash
# 添加基金
python -m src.cli.fund add --code 000001 --name "华夏成长" --class CSI300

# 设置定投
python -m src.cli.dca_plan add --fund 000001 --amount 1000 --freq monthly --rule 1

# 资产配置
python -m src.cli.alloc set --class CSI300 --target 0.6 --deviation 0.05
```

## 环境变量

- `DB_PATH`: SQLite 路径（默认 `data/portfolio.db`）
- `DISCORD_WEBHOOK_URL`: 日报推送地址
- `ENABLE_SQL_DEBUG`: SQL 日志开关

## 日历初始化

```bash
# A 股日历（推荐）
python -m src.cli.calendar sync --market CN_A --from 2020-01-01 --to 2025-12-31
python -m src.cli.calendar patch-cn-a --back 30 --forward 365
```

## 故障处理

**NAV 缺失**：`python -m src.cli.fetch_navs --date YYYY-MM-DD`
**交易延迟**：`python -m src.cli.trade confirm-manual --id ID --shares X --nav Y`
**数据库重建**：删除 `data/portfolio.db` 后重新初始化

---

详细规则见 `docs/settlement-rules.md`

---

## DCA 推断工具（dca_plan infer）

> 仅做只读分析，不会写入数据库，用于从历史买入记录中推断可能的定投模式，辅助你调整正式定投计划。

### 用法示例

```bash
# 从全部历史买入记录中推断定投候选（默认：样本数 ≥ 2，跨度 ≥ 7 天）
python -m src.cli.dca_plan infer

# 只分析某只基金
python -m src.cli.dca_plan infer --fund 001551

# 调整阈值：至少 6 个样本、跨度至少 30 天（提高门槛，减少候选）
python -m src.cli.dca_plan infer --min-samples 6 --min-span-days 30
```

### 参数说明

- `--min-samples`：最小样本数（买入笔数），默认 2；
- `--min-span-days`：样本覆盖的最小时间跨度（首尾交易日的日期差），默认 7 天；
- `--fund`：可选，只分析指定基金代码，默认分析所有基金。

### 输出示例

```text
[DCA:infer] 推断定投计划候选：min_samples=2, min_span_days=7, fund=ALL
共 2 个候选计划：
  ⭐ 001551 | monthly/10 | 1000 元 | samples=18, span=365 天, confidence=high | 2024-01-10 → 2024-12-10
  ✨ 110011 | weekly/MON | 500 元  | samples=8,  span=120 天, confidence=medium | 2024-03-04 → 2024-07-01
提示：请根据以上结果，使用 `dca_plan add` 手动创建/调整正式定投计划。
```

### 注意事项

- 仅读 `action_log` + `trades`：使用交易日期和金额做节奏分析
- 启发式规则：置信度分 `high/medium/low`
- 有交易日历时按交易日判断，无时回退自然日差
- 长假影响：日历模式下较弱，自然日差模式下可能漏报
---

## DCA 回填工具（dca_plan backfill）

> v0.4.3 新增：将历史导入的交易标记为 DCA 归属，用于数据追溯和AI分析。

### 用法示例

```bash
# 1. 干跑模式：检查批次 3 的匹配情况（不实际修改数据）
uv run python -m src.cli.dca_plan backfill --batch-id 3 --mode dry-run

# 2. 实际执行回填
uv run python -m src.cli.dca_plan backfill --batch-id 3 --mode apply

# 3. 只回填指定基金
uv run python -m src.cli.dca_plan backfill --batch-id 3 --fund 016532 --mode apply
```

### 参数说明

- `--batch-id`：导入批次 ID（必填，通过历史导入命令输出获得）；
- `--mode`：运行模式，`dry-run`（默认，仅检查）或 `apply`（实际执行）；
- `--fund`：可选，只回填指定基金代码，默认处理批次内所有基金。

### 回填逻辑

**匹配规则**：日期（daily/weekly/monthly）+ 金额（±10%）
**更新**：`trades.dca_plan_key` 和 `action_log.strategy` from `"none"` to `"dca"`

### 输出示例

```text
[DCA:backfill] 回填 DCA 归属（干跑）：batch_id=3, fund=ALL
[Backfill] 正在分析批次 3 的交易...
[Backfill] 发现 103 笔买入交易
[Backfill] 涉及 5 只基金

🔄 DCA 回填结果（dry-run 模式）
   Batch ID: 3
   基金范围: 全部
   总交易数: 103 笔（仅 buy）
   匹配 DCA: 12 笔
   匹配率: 11.7%

📊 基金匹配详情:
   ✅ 016532 (20 笔交易)
      定投计划: 100 元/monthly/28 (active)
      匹配结果: 8/20 笔
      样例:
        ✓ 2025-11-28: 100.00 元 - monthly: 28 == 28; 金额匹配: 100.00 ∈ [90, 110]
        ✓ 2025-10-28: 100.00 元 - monthly: 28 == 28; 金额匹配: 100.00 ∈ [90, 110]
        ✗ 2025-11-01: 150.00 元 - monthly: 1 != 28; 金额不符: 150.00 ∉ [90, 110]
        ... (还有 17 笔)

   ❌ 018044 (15 笔交易)
      ❌ 无定投计划（跳过）

提示：使用 --mode apply 执行实际回填
```

### 注意事项

- **前置条件**：必须先创建 DCA 计划（通过 `dca_plan add`）才能回填；
- **幂等安全**：可重复运行，不会产生副作用；
- **作用范围**：只回填 `import_batch_id IS NOT NULL` 的交易（历史导入数据）；
- **不修改事实字段**：只更新 `dca_plan_key` 和 `strategy`，不改 amount/trade_date/status；
- **回填可选**：不影响持仓和收益计算，主要用于数据追溯和 AI 分析；
- **金额浮动**：±10% 容差考虑用户可能微调定投金额的情况。
