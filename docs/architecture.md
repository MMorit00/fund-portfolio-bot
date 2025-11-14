# 架构说明（MVP）

本项目定位为个人基金投资的命令式 MVP，引擎以 Python 为主，采用“路径表达语义，文件名简短”的分层结构：

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

依赖方向：向内依赖
- adapters -> usecases.ports（Protocol）
- usecases -> core
- app 负责装配 Protocol 到具体适配器实现

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

## 架构图（PlantUML）

- 源文件：`docs/architecture/fund-portfolio-architecture.puml`
- 预览：使用 IDE PlantUML 插件或命令行 `plantuml docs/architecture/fund-portfolio-architecture.puml`
- 说明：本图以实际目录分组（`src/jobs`, `src/app`, `src/usecases`, `src/core`, `src/adapters`），仅展示当前仓库已有文件与关键依赖，突出核心流程与设计依赖关系。
