# 架构说明（MVP）

> 基础分层规则（core/usecases/adapters/app 依赖方向）详见 `.claude/skills/architecture/SKILL.md`。
> 本文档记录项目定位、技术选型、数据流设计等具体实现细节。

## 项目定位

本项目定位为个人基金投资的命令式 MVP，引擎以 Python 为主，采用"路径表达语义，文件名简短"的分层结构。

## 目录结构

```
src/
  core/         # 领域模型与业务规则（纯逻辑，不依赖外部实现）
  usecases/     # 用例（场景编排），依赖 core 与 ports（Protocol）
  adapters/     # 适配实现（SQLite / 数据源 / Discord）
  app/          # 启动、装配（wiring）、配置、轻量日志
  jobs/         # 定时/命令入口脚本（GitHub Actions 或本地 cron 调用）
docs/           # 文档（架构、规范、日志、路线图、归档）
data/           # SQLite 数据文件（默认 data/portfolio.db）
scripts/        # 辅助脚本（如备份）
```

不做/延后（MVP）：
- 不做 AI/NLU；不做历史导入；不做盘中估值；不做复杂前端
- 报告与再平衡均基于“每日官方净值”

命名与约定：
- 路径表达领域，文件名简洁：`usecases/trading/create_trade.py`、`core/trading/trade.py`
- Protocol 命名：`TradeRepo`、`NavProvider`、`ReportSender`（可后缀 `Protocol`）
- UseCase 类动宾命名：`CreateTrade`、`ConfirmPendingTrades`、`GenerateDailyReport`

错误与日志：
- 核心逻辑抛出异常；入口层捕获并 print 简短错误
- MVP 不引 logging 框架，仅提供 `app/log.py` 的 `log()` 薄封装
- SQL 打印通过 SQLite `set_trace_callback` 实现，受 `ENABLE_SQL_DEBUG` 控制

时间与精度：
- 时区统一 `Asia/Shanghai`; 日期格式 `YYYY-MM-DD`
- 金额、净值、份额使用 `decimal.Decimal`；统一保留位数与舍入策略

数据库（SQLite）：
- 表：`funds`、`trades`、`navs`、`dca_plans`、`alloc_config` 等
- 版本：`meta(schema_version)`；变更记录在 `docs/sql-migrations-*.md`
- 外键在 MVP 可不启用，应用层保证一致性

定时任务：
- `jobs/fetch_navs.py` 抓取每日官方净值
- `jobs/run_dca.py` 生成当日定投 pending 交易
- `jobs/confirm_trades.py` 按 T+N 规则确认份额
- `jobs/daily_report.py` 生成并发送日报（Discord Webhook）

## NAV 数据流（v0.3 草案）

- 外部数据源适配器：
  - `EastmoneyNavProvider`（`src/adapters/datasources/eastmoney_nav.py`）
    - 使用 httpx 同步客户端，从东方财富接口按“基金代码 + 日期”获取官方单位净值；
    - 处理超时/重试/HTTP 状态码与解析错误，所有异常收敛为可选值（失败返回 None）。
- 本地净值仓储：
  - `SqliteNavRepo`（`src/adapters/db/sqlite/nav_repo.py`）
    - 表：`navs(fund_code, day, nav)`；
    - 接口：`upsert()` + `get()`，以文本形式持久化 Decimal。
- 运行时 Provider：
  - `LocalNavProvider`（`src/adapters/datasources/local_nav.py`）
    - 仅从本地 `navs` 表读取 NAV，供用例 `ConfirmPendingTrades`、`GenerateDailyReport`、`GenerateRebalanceSuggestion` 使用；
    - 不直接访问外部 HTTP。
- 数据流整体关系：
  1. Job `fetch_navs` 通过 `EastmoneyNavProvider` 从外部拉取某日 NAV；
  2. 调用 `SqliteNavRepo.upsert` 落地到 `navs` 表（按 fund_code+day 幂等）；
  3. 运行确认/日报时，通过 `LocalNavProvider` 从 `navs` 读取对应日期 NAV；
  4. 核心用例与领域层只感知 `NavProvider` 接口，不关心外部数据源细节。

## 架构图（PlantUML）

- 源文件：`docs/architecture/fund-portfolio-architecture.puml`
- 预览：使用 IDE PlantUML 插件或命令行 `plantuml docs/architecture/fund-portfolio-architecture.puml`
- 说明：本图以实际目录分组（`src/jobs`, `src/app`, `src/usecases`, `src/core`, `src/adapters`），仅展示当前仓库已有文件与关键依赖，突出核心流程与设计依赖关系。

## 日历与确认（v0.3 核心补充）

- 策略对象：`src/core/trading/policy.py` 定义 `SettlementPolicy`，结合 `DateMath`（`src/core/trading/date_math.py`）实现“卫兵+定价+计数”的组合策略。
- 日历存取：`src/adapters/db/sqlite/calendar_store.py` 从 `trading_calendar` 表读取，采用严格模式（缺失即报错）。
- 注油与修补：
  - 注油：`src/jobs/sync_calendar.py`（exchange_calendars），仅写到“日历最大已知日期”。
  - 修补：`src/jobs/patch_calendar.py`（Akshare/新浪），仅写到“数据源最大已知日期”。
- 交易表持久化：`trades.pricing_date` 入库，确认严格按定价日 NAV；`SCHEMA_VERSION=3`。
