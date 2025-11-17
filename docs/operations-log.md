# Operations Log（环境/工具/运维）

## 2025-11-14 初始化

- 创建基础目录结构：`src/core`, `src/usecases`, `src/adapters`, `src/app`, `src/jobs`, `docs`, `scripts`, `data`
- 约定：敏感信息走环境变量（`.env` 不入库）；CI 使用 Secrets；配置入口 `src/app/config.py`
- SQL 打印策略：SQLite `set_trace_callback`（受 `ENABLE_SQL_DEBUG` 控制）
- 备份策略：`scripts/backup_db.sh` 手动快照（重大变更前执行）

## 2025-11-15 手动录入交易（CLI）

### 使用方法

**买入基金**：
```bash
python -m src.app.main buy --fund-code 110022 --amount 1000
python -m src.app.main buy --fund-code 110022 --amount 1000.50 --date 2025-11-15
```

**卖出基金**：
```bash
python -m src.app.main sell --fund-code 000001 --amount 500
python -m src.app.main sell --fund-code 000001 --amount 500.50 --date 2025-11-16
```

### 参数说明
- `--fund-code`（必需）：基金代码，必须已在 funds 表中配置
- `--amount`（必需）：交易金额，支持整数或小数（如 1000 或 1000.50）
- `--date`（可选）：交易日期，格式为 YYYY-MM-DD，默认今天

### 输出示例

**成功**：
```
✅ 交易已创建：ID=2 fund=110022 type=buy amount=1000 date=2025-11-15 confirm_date=2025-11-17
```

**错误（基金不存在）**：
```
❌ 错误：未知基金代码：999999
提示：请检查是否已在 funds 表中配置，或先运行 dev_seed_db
```

**错误（金额格式无效）**：
```
❌ 错误：金额格式无效：abc（期望 Decimal，例如 1000 或 1000.50）
```


## 2025-11-15 开发自测流程

### v0.1 完整流程验证

以下是本地开发环境的自测步骤，用于验证从交易录入到日报生成的完整闭环：

**步骤 1：初始化数据库**
```bash
# 运行 seed 脚本，创建测试数据
PYTHONPATH=. python scripts/dev_seed_db.py
```

**步骤 2：手动录入交易（可选）**
```bash
# 使用 CLI 录入新交易
python -m src.app.main buy --fund-code 110022 --amount 1000
python -m src.app.main sell --fund-code 000001 --amount 500.50 --date 2025-11-16
```

**步骤 3：模拟定投生成**
```bash
# 运行定投 job（如果今天符合定投规则）
python -m src.jobs.run_dca
```

**步骤 4：确认交易份额**
```bash
# 确认到期的 pending 交易
python -m src.jobs.confirm_trades
```

**步骤 5：生成日报**
```bash
# 生成并查看日报内容
python -m src.jobs.daily_report
```

### 日报输出示例

```
【持仓日报 2025-11-15】
总份额：666.67

资产配置：
- CGB_3_5Y：0.0% (目标 20.0%，低配 -20.0%)
- CSI300：100.0% (目标 50.0%，超配 +50.0%)
- US_QDII：0.0% (目标 30.0%，低配 -30.0%)

⚠️ 再平衡提示：
- CSI300 超配，建议减持
- US_QDII 低配，建议增持
- CGB_3_5Y 低配，建议增持
```

### 注意事项

1. **NAV 数据要求**：
   - 当前版本使用本地 NAV（方案 A）
   - `confirm_trades` 需要对应日期的 NAV 数据才能确认交易
   - 可通过 `dev_seed_db.py` 或手动插入 NAV 数据

2. **日报内容说明**：
   - 当前版本显示"总份额"而非"总市值"
   - 权重计算基于份额归一化，不依赖 NAV
   - 适用于快速查看配置偏离情况

3. **Discord 推送**：
   - 需要配置 `DISCORD_WEBHOOK_URL` 环境变量
   - 未配置时日报仍会生成，但不会推送

## 2025-11-20 NAV 抓取 Job（v0.3 草案）

### 使用方法

抓取今天全部基金的 NAV：

```
python -m src.jobs.fetch_navs
```

抓取指定日期的 NAV：

```
python -m src.jobs.fetch_navs --date 2025-11-20
```

说明：
- Job 会遍历 `funds` 表中已配置的所有基金；
- 对每只基金调用 `EastmoneyNavProvider.get_nav(fund_code, day)` 获取官方单位净值；
- 仅当返回值存在且 > 0 时，才会写入 `navs` 表（`upsert`，幂等）；
- 获取失败或 NAV 无效时，记录基金代码到失败列表，并在 Job 结束时打印提示。

依赖与请求说明：
- 依赖 `httpx`；建议使用 UV 安装：`uv add httpx`（或 `pip install httpx`）。
- Eastmoney 接口：`https://api.fund.eastmoney.com/f10/lsjz`（按日历史净值）。
- 请求头：已在 Provider 固定 `User-Agent`、`Referer: https://fundf10.eastmoney.com/`、`Accept: application/json`，以减少 403 风险。

### 推荐调度顺序（本地 cron / GitHub Actions）

在每天交易日结束后按顺序执行：

```
python -m src.jobs.fetch_navs      # 抓取 NAV
python -m src.jobs.confirm_trades  # 确认到期 pending
python -m src.jobs.daily_report    # 生成并推送日报
```

如需对历史日期补 NAV 与确认，可先对指定日期运行：

```
python -m src.jobs.fetch_navs --date YYYY-MM-DD
python -m src.jobs.confirm_trades  # （未来可扩展 --day 参数）
```

## 2025-11-21 交易日历导入与确认重跑（v0.3）

### 导入交易日历（SQLite）

CSV 放置建议：`data/trading_calendar/a_shares.csv`，表头支持：
- `market,day,is_trading_day`（更通用）或 `day,is_trading_day`（market 默认 A）

示例命令：

```
DB_PATH=data/portfolio.db \
python scripts/import_trading_calendar.py data/trading_calendar/a_shares.csv
```

启用 DB 版交易日历：

```
TRADING_CALENDAR_BACKEND=db \
DB_PATH=data/portfolio.db \
python -m src.jobs.confirm_trades
```

注意：当 `TRADING_CALENDAR_BACKEND=db` 且未找到 `trading_calendar` 表时，会报错退出。

### 补录 NAV 后补确认

```
# 1) 补录当日官方 NAV
python -m src.jobs.fetch_navs --date YYYY-MM-DD

# 2) 对该日重跑确认
python -m src.jobs.confirm_trades --day YYYY-MM-DD
```

确认任务输出会统计：成功确认数量、因定价日 NAV 缺失而跳过的数量与涉及基金代码。

## 2025-11-21 日志规范约定

### 日志前缀规范

为便于后续日志分析与定位，各适配器的 print 日志应使用统一前缀：

- **EastmoneyNavProvider**：`[EastmoneyNav]` - 东方财富净值数据源相关日志
- **LocalNavProvider**：`[LocalNav]` - 本地 SQLite NAV 仓储日志
- **DiscordReportSender**：`[Discord]` - Discord Webhook 推送日志
- **通用 Job**：`[Job:xxx]` - 定时任务脚本日志，如 `[Job:fetch_navs]`、`[Job:confirm_trades]`

### 日志内容约定

1. **错误与异常**：包含足够上下文（fund_code、day、attempt 等）以便排查
2. **状态提示**：成功/失败统计信息使用 `✅` / `⚠️` 前缀增强可读性
3. **详细模式**：保留 `ENABLE_SQL_DEBUG` 环境变量控制 SQL trace 输出

### 示例

```
[EastmoneyNav] 获取 NAV 失败：fund=110022 day=2025-11-20 attempt=2 err=ConnectTimeout
[LocalNav] 成功写入 NAV：fund=110022 day=2025-11-20 nav=1.2345
[Discord] Webhook 推送失败：status=400 msg="Invalid request"
[Job:fetch_navs] ✅ 抓取完成：成功 45/50，失败 5 只
```
