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

- 工具只读取 `action_log` + `trades`：
  - 仅使用 `action='buy'` 且 `source in ('manual', 'import')` 的行为；
  - 通过 `trade_id` 关联到对应交易，使用交易日期与金额做节奏分析；
- 判断规则为启发式，不能保证 100% 准确：
  - 若已初始化交易日历（`trading_calendar`+CalendarService 可用）：
    - 使用“交易日数量”作为间隔单位：
      - 日度：90% 以上间隔为 1 个交易日以内；
      - 周度：80% 以上间隔在 4–6 个交易日；
      - 月度：80% 以上间隔在 18–25 个交易日；
  - 若未初始化交易日历（或日历数据缺失）：
    - 回退为“自然日差”判断：
      - 日度：90% 以上间隔在 2 天以内；
      - 周度：80% 以上间隔在 6–8 天；
      - 月度：80% 以上间隔在 28–32 天；
- 置信度说明：
  - `high`：样本多、节奏稳定，较可能是真实定投计划；
  - `medium`：样本和节奏基本合理，需要你人工再判断；
  - `low`：当前实现中通常已被阈值过滤，仅作为兜底等级。
 - 在使用交易日历模式时，春节/国庆等长假对 daily/weekly 模式的影响会显著减弱；
   若日历数据缺失导致回退到自然日差，则长假仍可能拉低识别率（偏保守漏报）。
