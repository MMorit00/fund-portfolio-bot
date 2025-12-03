# 运维手册（当前操作）

> 本文档记录当前版本的操作命令与配置方式。
> 历史决策与演进见 `docs/coding-log.md`。

## 环境准备

### 依赖管理

本项目使用 **uv** 管理 Python 依赖：

```bash
# 安装依赖
uv sync

# 运行命令（重要！）
uv run python -m src.cli.xxx
```

### 环境变量配置

敏感信息通过环境变量 / `.env` 提供：
- `DISCORD_WEBHOOK_URL`：日报推送地址
- `DB_PATH`：SQLite 路径（默认 `data/portfolio.db`）
- `ENABLE_SQL_DEBUG`：是否启用 SQL trace 打印

配置统一在 `src/core/config.py` 读取。

## CLI 命令速查表

| 分类 | 命令 | 说明 |
|------|------|------|
| **配置管理** | | |
| | `fund add` | 添加基金 |
| | `fund list` | 查看基金列表 |
| | `fund remove` | 删除基金 |
| | `fund sync-fees` | 同步费率（从东方财富）|
| | `fund fees` | 查看基金费率 |
| | `dca_plan add` | 添加定投计划 |
| | `dca_plan list` | 查看定投计划 |
| | `dca_plan enable/disable` | 启用/禁用定投 |
| | `dca_plan delete` | 删除定投计划 |
| | `alloc set` | 设置资产配置目标 |
| | `alloc show` | 查看资产配置 |
| | `alloc delete` | 删除资产配置 |
| **交易确认** | | |
| | `trade buy` | 手动买入交易 |
| | `trade sell` | 手动卖出交易 |
| | `trade list` | 查询交易记录 |
| | `trade cancel` | 取消 pending 交易 |
| | `trade confirm-manual` | 手动确认交易（NAV 缺失场景）|
| | `confirm` | 自动确认到期交易 |
| | `dca run` | 执行定投（创建交易）|
| | `dca skip` | 跳过定投 |
| **数据报告** | | |
| | `fetch_navs` | 抓取净值（单日/指定基金）|
| | `fetch_navs_range` | 批量抓取净值（日期区间）|
| | `report` | 生成日报（市值/份额视图）|
| | `rebalance` | 再平衡建议（独立查看）|
| | `market_value` | 持仓市值查询 |
| **行为数据** | | |
| | `action list` | 查询行为日志 |
| **日历管理** | | |
| | `calendar refresh` | 从 CSV 刷新日历 |
| | `calendar sync` | 使用 exchange_calendars 同步 |
| | `calendar patch-cn-a` | 使用 Akshare 修补 A 股日历 |

> 每个命令的详细用法和参数见下文各章节。

## 数据库初始化

```bash
# 重建测试数据库（开发阶段，推荐）
rm data/portfolio.db  # 删除旧库
SEED_RESET=1 PYTHONPATH=. python -m scripts.dev_seed_db

# 备份数据库（重大变更前）
./scripts/backup_db.sh
```

**Schema 管理**：
- 当前版本：以 `docs/sql-schema.md` 为准（开发阶段每次 Schema 变更建议删库重建）
- 开发阶段直接删除重建，无需迁移脚本

## 日常运维流程（推荐）

### 方案 A：早上定时执行（推荐）

```bash
# 每天早上 9:00 自动运行（展示昨天的数据）
python -m src.cli.dca              # 1. 执行定投（创建今日 pending 交易，支持 --date 补录）
python -m src.cli.fetch_navs       # 2. 抓取昨日 NAV（默认，因今日 NAV 通常晚上才公布）
python -m src.cli.confirm          # 3. 确认昨日创建的交易
python -m src.cli.report           # 4. 生成日报（默认展示昨日数据）
```

**说明**：
- `dca` 默认创建今日交易，可用 `--date YYYY-MM-DD` 补录历史定投
- `fetch_navs` 默认抓"上一工作日"的 NAV，因为当日 NAV 通常在 18:00-22:00 后才公布
- `report` 默认展示"上一工作日"的持仓，与 `fetch_navs` 保持一致
- 今日创建的交易会在明天确认（T+1）

### 方案 B：晚上补充执行（可选）

```bash
# 晚上 22:00 后手动运行（抓取今日NAV）
python -m src.cli.fetch_navs --date $(date +%Y-%m-%d)  # 抓今日NAV
python -m src.cli.report --as-of $(date +%Y-%m-%d)     # 查看今日持仓

# 次日早上confirm时，昨天创建的交易就能被确认
```

**说明**：
- 如需查看今日最新净值，晚上手动执行
- 为次日早上的 `confirm` 准备好今日 NAV

> NAV 策略、确认规则、再平衡触发条件见 `docs/settlement-rules.md`。

## 配置管理

### 基金配置

```bash
# 添加基金
python -m src.cli.fund add --code 000001 --name "华夏成长" --class CSI300 --market CN_A
python -m src.cli.fund add --code 110022 --name "易方达中小盘混合" --class CSI300 --market CN_A
python -m src.cli.fund add --code 161125 --name "标普500" --class US_QDII --market US_NYSE

# 查看所有基金
python -m src.cli.fund list
```

### 基金费率管理（v0.4.3+）

```bash
# 同步所有基金费率（从东方财富抓取）
python -m src.cli.fund sync-fees

# 同步单只基金费率
python -m src.cli.fund sync-fees --code 110022

# 查看基金费率
python -m src.cli.fund fees --code 110022
```

**费率字段说明**：
- 管理费率/托管费率/销售服务费率：年化费率，从净值中每日扣除，无需另行支付
- 申购费率（原）：基金公司标准费率
- 申购费率（折扣）：天天基金平台优惠费率

### 定投计划管理

```bash
# 添加定投计划
python -m src.cli.dca_plan add --fund 000001 --amount 1000 --freq monthly --rule 1
python -m src.cli.dca_plan add --fund 110022 --amount 500 --freq weekly --rule MON
python -m src.cli.dca_plan add --fund 161125 --amount 200 --freq daily --rule ""

# 查看定投计划
python -m src.cli.dca_plan list              # 全部
python -m src.cli.dca_plan list --active-only # 仅活跃

# 禁用/启用定投计划
python -m src.cli.dca_plan disable --fund 000001
python -m src.cli.dca_plan enable --fund 000001
```

### 资产配置目标

```bash
# 设置配置（权重为小数，如 0.6 表示 60%）
python -m src.cli.alloc set --class CSI300 --target 0.6 --deviation 0.05
python -m src.cli.alloc set --class US_QDII --target 0.3 --deviation 0.05
python -m src.cli.alloc set --class CGB_3_5Y --target 0.1 --deviation 0.03

# 查看配置（会提示总权重是否为 100%）
python -m src.cli.alloc show
```

### 手动交易

```bash
# 买入
python -m src.cli.trade buy --fund 110022 --amount 1000
python -m src.cli.trade buy --fund 110022 --amount 1000.50 --date 2025-11-15

# 卖出
python -m src.cli.trade sell --fund 000001 --amount 500 --date 2025-11-16

# 查询交易记录
python -m src.cli.trade list                    # 全部交易
python -m src.cli.trade list --status pending   # 待确认
python -m src.cli.trade list --status confirmed # 已确认

# 取消 pending 交易
python -m src.cli.trade cancel --id 123

# 手动确认（NAV 永久缺失场景）
python -m src.cli.trade confirm-manual --id 123 --shares 404.86 --nav 1.234
```

### 补录历史 NAV

```bash
# 单日抓取
python -m src.cli.fetch_navs --date 2025-11-20

# 区间抓取（闭区间，幂等）
python -m src.cli.fetch_navs_range --from 2025-01-01 --to 2025-03-31

# 补录后重跑确认
python -m src.cli.confirm --day 2025-04-01
```

### 市值查询（v0.4.2+）

用于查询指定日期的持仓市值（可用于导入后验证、日常对账等）：

```bash
# 查看市值（默认：上一交易日，回退到最近有净值的交易日）
python -m src.cli.market_value

# 指定日期
python -m src.cli.market_value --as-of 2025-11-29

# 使用估值模式（当官方净值缺失时用盘中估值）
python -m src.cli.market_value --estimate
```

**回退策略**：
- 默认（净值模式）：向前查找最近 7 个交易日的官方净值
- `--estimate`：使用盘中估值（仅限最近 3 天）

---

## 再平衡管理

### 功能说明

独立再平衡 CLI，提供：
- 快速查看资产配置状态和再平衡建议（无需跑完整日报）
- 具体到基金级别的调仓建议（而非仅资产类别）
- 智能买入/卖出策略（平均化 vs 渐进式减仓）

### 基本用法

```bash
# 查看当前再平衡建议（默认：上一交易日）
python -m src.cli.rebalance

# 查看指定日期的再平衡建议
python -m src.cli.rebalance --as-of 2025-01-20

# 查看帮助
python -m src.cli.rebalance --help
```

### 输出示例

```
📊 再平衡建议（2025-11-21）

总市值：¥2,964.17

当前资产配置：
  CSI300: 100.0% (目标 50.0%) ⚠️ 偏高 50.0%
  US_QDII: 0.0% (目标 30.0%) ⚠️ 偏低 30.0%
  CGB_3_5Y: 0.0% (目标 20.0%) ⚠️ 偏低 20.0%

调仓建议：
  CSI300：建议卖出 ¥741
    • [110022] 易方达沪深300ETF联接：¥741 (当前占比 100.0%)
  US_QDII：建议买入 ¥445
  CGB_3_5Y：建议买入 ¥296
```

### 状态说明

- **✓ 正常**：当前权重在目标范围内（偏离 ≤ 5%）
- **💡 偏低/偏高**：轻微偏离（5% < 偏离 ≤ 10%）
- **⚠️ 偏低/偏高**：明显偏离（偏离 > 10%）

### 基金建议策略

**买入策略（平均化持仓）**：
- 优先推荐该资产类别下当前持仓较小的基金
- 目的：避免单只基金占比过大，分散风险

**卖出策略（渐进式减仓）**：
- 优先推荐持仓较大的基金
- 目的：避免一次性清仓小持仓基金，保持流动性

### 使用场景

**场景 1：快速查看再平衡建议**
```bash
# 早上执行完日常流程后，单独查看再平衡建议
python -m src.cli.dca
python -m src.cli.fetch_navs
python -m src.cli.confirm
python -m src.cli.rebalance  # ✅ 快速查看，无需等待日报生成
```

**场景 2：周末规划下周调仓**
```bash
# 周六查看上周五的建议
python -m src.cli.rebalance --as-of 2025-01-17

# 根据输出的具体基金代码和金额，规划下周交易
```

**场景 3：配合手动交易**
```bash
# 1. 查看建议
python -m src.cli.rebalance

# 2. 执行建议的交易
python -m src.cli.trade buy --fund 513500 --amount 2400
python -m src.cli.trade sell --fund 110022 --amount 741

# 3. 再次查看（验证）
python -m src.cli.rebalance
```

### 注意事项

1. **NAV 依赖**：
   - 再平衡计算依赖当日 NAV
   - 如果 NAV 缺失，会提示"当日 NAV 缺失，无法给出金额建议"
   - 建议先运行 `python -m src.cli.fetch_navs` 确保 NAV 数据完整

2. **默认日期**：
   - 默认展示"上一交易日"（与日报一致）
   - 原因：当日 NAV 通常晚上才公布，早上运行时使用昨日数据更稳定

3. **建议性质**：
   - 再平衡建议仅供参考，不自动执行
   - 用户需根据实际情况（市场判断、资金可用性等）决定是否调仓

---

## 日志前缀规范

为便于日志分析，各适配器使用统一前缀：

| 前缀 | 含义 |
|-----|------|
| `[EastmoneyNav]` | 东方财富净值数据源 |
| `[LocalNav]` | 本地 SQLite NAV 仓储 |
| `[Discord]` | Discord Webhook 推送 |
| `[Job:xxx]` | 定时任务脚本（如 `[Job:fetch_navs]`） |

示例：
```
[EastmoneyNav] 获取 NAV 失败：fund=110022 day=2025-11-20 attempt=2
[Job:fetch_navs] ✅ 抓取完成：成功 45/50，失败 5 只
```

## 交易日历管理（v0.3.4+）

v0.3.4 统一使用 DB 日历后端，通过 `calendar` CLI 管理日历数据。提供三种日历管理方式：

| 命令 | 用途 | 数据源 | 场景 |
|------|------|--------|------|
| `refresh` | CSV 导入 | 手动准备的 CSV | 离线场景/自定义日历 |
| `sync` | 基础日历注油 | exchange_calendars | 首次初始化历史数据 |
| `patch-cn-a` | A 股日历修补 | Akshare + 新浪财经 | 日常修补临时调休 |

### 方案 A：exchange_calendars 注油 + Akshare 修补（推荐）

**适用场景**：国内 A 股投资，需要自动同步最新交易日历。

```bash
# 1. 首次初始化：使用 exchange_calendars 同步历史数据
python -m src.cli.calendar sync --market CN_A --from 2020-01-01 --to 2025-12-31

# 2. 日常修补：使用 Akshare 修补近期 A 股日历
python -m src.cli.calendar patch-cn-a --back 30 --forward 365
```

**依赖说明**：
- `exchange-calendars` 和 `akshare` 已在 `pyproject.toml` 中声明为项目依赖
- 安装项目时会自动安装这些库（`uv sync`）

**说明**：
- `sync` 提供"骨架"（官方标准日历，覆盖历史 + 已知未来）
- `patch-cn-a` 提供"补丁"（新浪财经实时数据，修正临时调休/节假日变更）
- **推荐定期执行** `patch-cn-a`（如每周/每月），确保日历最新
- 支持其他市场：`--market US_NYSE`（美股）

### 方案 B：纯 CSV 导入（离线场景）

**适用场景**：无法安装外部依赖、完全自定义日历、离线环境。

```bash
# 从预先准备的 CSV 导入
python -m src.cli.calendar refresh --csv data/trading_calendar_cn_a.csv

# 支持多市场导入
python -m src.cli.calendar refresh --csv data/trading_calendar_us_nyse.csv
```

**CSV 格式支持**：
- 完整格式：`market,day,is_trading_day`
- 简化格式：`day,is_trading_day`（market 默认 CN_A）

### 首次使用要求

- 系统要求 `trading_calendar` 表必须存在且有数据
- **首次运行任何 CLI 前，必须先初始化日历**（使用上述任一方案）
- 否则会抛出明确错误提示

### 验证日历数据

```bash
# 月度统计
sqlite3 data/portfolio.db "SELECT market, COUNT(*) AS total, SUM(is_trading_day) AS opens FROM trading_calendar GROUP BY market;"

# 点查（国庆场景）
sqlite3 data/portfolio.db "SELECT * FROM trading_calendar WHERE market='CN_A' AND day='2025-10-01';"

# 查看最新修补日期
sqlite3 data/portfolio.db "SELECT market, MAX(day) FROM trading_calendar WHERE is_trading_day=1 GROUP BY market;"
```

## 确认延迟处理

### 查看延迟交易

```sql
SELECT fund_code, type, amount, trade_date, confirm_date, delayed_reason, delayed_since,
       julianday('now') - julianday(confirm_date) as days_delayed
FROM trades
WHERE confirmation_status = 'delayed'
ORDER BY delayed_since;
```

### 补录 NAV 后重新确认

```bash
# 1. 补录缺失 NAV
python -m src.cli.fetch_navs --date 2025-11-15

# 2. 重跑确认（自动处理延迟交易）
python -m src.cli.confirm
```

### 手动确认交易（NAV 永久缺失场景）

如果支付宝订单已成功但系统 NAV 持续缺失（基金停牌、数据源故障），可手动确认：

```bash
# 从支付宝复制份额和净值，手动确认交易
python -m src.cli.trade confirm-manual --id 123 --shares 404.86 --nav 1.234
```

**注意**：
- 仅用于 pending 状态交易，确认后无法撤销
- NAV 和份额必须从支付宝等平台准确复制
- 优先使用 `fetch_navs` 补数据，手动确认作为最后手段
- 延迟超过 3 天建议先到支付宝核实订单状态
