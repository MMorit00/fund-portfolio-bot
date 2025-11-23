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

## 日常 Job 调度（推荐顺序）

```bash
# 假设上一交易日为 T
python -m src.cli.fetch_navs --date T      # 抓取 T 日 NAV
python -m src.cli.confirm --day T+1        # 确认到期交易
python -m src.cli.report --as-of T         # 生成日报（展示日=T）
```

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
