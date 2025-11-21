# 运维手册（当前操作）

> 本文档记录当前版本的操作命令与配置方式。
> 历史决策与演进见 `docs/coding-log.md`。

## 环境配置

敏感信息通过环境变量 / `.env` 提供：
- `DISCORD_WEBHOOK_URL`：日报推送地址
- `DB_PATH`：SQLite 路径（默认 `data/portfolio.db`）
- `ENABLE_SQL_DEBUG`：是否启用 SQL trace 打印
- `TRADING_CALENDAR_BACKEND`：交易日历后端（`db` 或默认 `simple`）

配置统一在 `src/app/config.py` 读取。

## 数据库初始化

```bash
# 重建测试数据库（开发阶段）
SEED_RESET=1 PYTHONPATH=. python -m scripts.dev_seed_db

# 备份数据库（重大变更前）
./scripts/backup_db.sh
```

## 日常 Job 调度（推荐顺序）

```bash
# 假设上一交易日为 T
python -m src.jobs.fetch_navs --date T      # 抓取 T 日 NAV
python -m src.jobs.confirm_trades --day T+1 # 确认到期交易
python -m src.jobs.daily_report --as-of T   # 生成日报（展示日=T）
```

> NAV 策略、确认规则、再平衡触发条件见 `docs/settlement-rules.md`。

## CLI 常用命令

### 手动录入交易

```bash
# 买入
python -m src.app.main buy --fund-code 110022 --amount 1000
python -m src.app.main buy --fund-code 110022 --amount 1000.50 --date 2025-11-15

# 卖出
python -m src.app.main sell --fund-code 000001 --amount 500 --date 2025-11-16
```

参数：
- `--fund-code`（必需）：基金代码（必须已在 `funds` 表中）
- `--amount`（必需）：交易金额
- `--date`（可选）：交易日期，默认今天

### 查看持仓状态

```bash
# 默认上一交易日市值视图
python -m src.app.main status

# 指定视图与展示日
python -m src.app.main status --mode market --as-of 2025-11-12
python -m src.app.main status --mode shares --as-of 2025-11-12
```

### 补录历史 NAV

```bash
# 单日抓取
python -m src.jobs.fetch_navs --date 2025-11-20

# 区间抓取（闭区间，幂等）
python -m src.jobs.fetch_navs_range --from 2025-01-01 --to 2025-03-31

# 补录后重跑确认
python -m src.jobs.confirm_trades --day 2025-04-01
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
  python -m src.jobs.sync_calendar --cal CN_A --from 2024-01-01 --to 2030-12-31

# 修补（Akshare/新浪，在线覆盖）
DB_PATH=data/portfolio.db python -m src.jobs.patch_calendar
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
python -m src.jobs.fetch_navs --date 2025-11-15

# 2. 重跑确认（自动处理延迟交易）
python -m src.jobs.confirm_trades
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
