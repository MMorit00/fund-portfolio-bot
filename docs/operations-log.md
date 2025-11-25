# 运维手册（当前操作）

> 本文档记录当前版本的操作命令与配置方式。
> 历史决策与演进见 `docs/coding-log.md`。

## 环境配置

敏感信息通过环境变量 / `.env` 提供：
- `DISCORD_WEBHOOK_URL`：日报推送地址
- `DB_PATH`：SQLite 路径（默认 `data/portfolio.db`）
- `ENABLE_SQL_DEBUG`：是否启用 SQL trace 打印
- `TRADING_CALENDAR_BACKEND`：交易日历后端（`db` 或默认 `simple`）

配置统一在 `src/core/config.py` 读取。

## 数据库初始化

```bash
# 重建测试数据库（开发阶段，推荐）
rm data/portfolio.db  # 删除旧库
SEED_RESET=1 PYTHONPATH=. python -m scripts.dev_seed_db

# 备份数据库（重大变更前）
./scripts/backup_db.sh
```

**Schema 管理（v0.3.2）**：
- 当前开发阶段：使用 `CREATE TABLE IF NOT EXISTS`，**无自动迁移**
- `SCHEMA_VERSION = 4`（仅用于标识版本，不含迁移逻辑）
- **开发建议**：测试数据库直接删除重建，无需迁移
- **未来生产**：需要时可添加版本检测与 ALTER 迁移逻辑

## 日常运维流程（推荐）

### 方案 A：早上定时执行（推荐）

```bash
# 每天早上 9:00 自动运行（展示昨天的数据）
python -m src.cli.dca              # 1. 执行定投（创建今日pending交易）
python -m src.cli.fetch_navs       # 2. 抓取昨日NAV（默认，因今日NAV通常晚上才公布）
python -m src.cli.confirm          # 3. 确认昨日创建的交易
python -m src.cli.report           # 4. 生成日报（默认展示昨日数据）
```

**说明**：
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

## v0.3.2 配置管理 CLI

### 基金配置

```bash
# 添加基金
python -m src.cli.fund add --code 000001 --name "华夏成长" --class CSI300 --market CN_A
python -m src.cli.fund add --code 110022 --name "易方达中小盘混合" --class CSI300 --market CN_A
python -m src.cli.fund add --code 161125 --name "标普500" --class US_QDII --market US_NYSE

# 查看所有基金
python -m src.cli.fund list
```

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

---

## v0.3.3 再平衡独立 CLI

### 功能说明

v0.3.3 新增独立再平衡 CLI，提供：
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

## 交易日历管理（v0.3）

### 导入交易日历

CSV 格式：`market,day,is_trading_day` 或 `day,is_trading_day`（market 默认 A）

```bash
# 注油（exchange_calendars）
TRADING_CALENDAR_BACKEND=db DB_PATH=data/portfolio.db \
  python -m src.cli.sync_calendar --cal CN_A --from 2024-01-01 --to 2030-12-31

# 修补（Akshare/新浪，在线覆盖）
DB_PATH=data/portfolio.db python -m src.cli.patch_calendar
```

### 验证日历数据

```bash
# 月度统计
sqlite3 data/portfolio.db "SELECT market, COUNT(*) AS total, SUM(is_trading_day) AS opens FROM trading_calendar GROUP BY market;"

# 点查（国庆场景）
sqlite3 data/portfolio.db "SELECT * FROM trading_calendar WHERE market='CN_A' AND day='2025-10-01';"
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

### 手动标记已确认（异常场景）

如果支付宝订单已成功但系统 NAV 缺失，可手动更新：

```sql
UPDATE trades
SET status = 'confirmed', shares = 404.86,  -- 从支付宝复制
    confirmation_status = 'normal', delayed_reason = NULL, delayed_since = NULL
WHERE id = 123;
```

**注意**：
- 不要修改 `confirm_date`（用于追踪延迟时长）
- 优先使用 `fetch_navs` 补数据
- 延迟超过 3 天建议到支付宝核实订单状态
