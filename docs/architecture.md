# 架构说明

> 本文档说明项目定位、技术选型、分层架构与数据流设计。

## 项目定位

个人基金投资的命令式工具，采用 Python 实现，目录结构清晰，职责分明。

## 目录结构

```
src/
  cli/          # 命令行入口（原 jobs/）
  flows/        # 业务流程编排（原 usecases/）
  core/         # 核心逻辑（配置 + 模型 + 规则）
    ├─ models/  #   领域数据类（Trade, Fund, DcaPlan 等）
    └─ rules/   #   纯业务规则函数（Settlement, Rebalance, Precision）
  data/         # 数据访问层（原 adapters/）
    ├─ db/      #   数据库 Repo（TradeRepo, NavRepo 等）
    └─ client/  #   外部客户端（Eastmoney, Discord 等）

docs/          # 文档
data/          # SQLite 数据文件（默认 data/portfolio.db）
scripts/       # 辅助脚本
```

## 分层架构（v0.3.1 简化版）

```
┌─────────────────────────────────────────────────────────────┐
│                   src/cli（命令行入口）                       │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  CLI: 参数解析 + 流程函数（xxx_flow）                  │  │
│  │  - confirm.py:  confirm_trades_flow()                │  │
│  │  - dca.py:      run_dca_flow()                       │  │
│  │  - report.py:   daily_report_flow()                  │  │
│  │  - 直接实例化 Repo: TradeRepo(conn, calendar)        │  │
│  └───────────────────────────────────────────────────────┘  │
└────────────┬────────────────────────────┬───────────────────┘
             │                            │
             │ 调用                        │ 调用
             ▼                            ▼
┌────────────────────────────┐    ┌──────────────────────────┐
│  src/flows（业务流程）      │    │  src/data（数据访问）      │
│ ┌────────────────────────┐ │    │ ┌──────────────────────┐ │
│ │  业务类（精简后）       │ │    │ │ db/                  │ │
│ │  - CreateTrade         │ │    │ │   TradeRepo          │ │
│ │  - ConfirmTrades       │ │    │ │   NavRepo            │ │
│ │  - MakeDailyReport     │ │    │ │   CalendarService    │ │
│ │  返回 Result dataclass │ │    │ ├──────────────────────┤ │
│ └────────────────────────┘ │    │ │ client/              │ │
└────────────┬───────────────┘    │ │   EastmoneyService   │ │
             │                    │ │   LocalNavService    │ │
             │                    │ │   DiscordService     │ │
             │ 使用模型             │ └──────────────────────┘ │
             ▼                    └────────────┬─────────────┘
┌─────────────────────────────────────────────┴──────────────┐
│             src/core（核心逻辑，纯数据）                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ models/  → Trade, Fund, DcaPlan, AssetClass          │  │
│  │ rules/   → settlement, rebalance, precision (纯函数) │  │
│  │ config.py, log.py                                    │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘

                         外部系统
    ┌──────────┐  ┌──────────────┐  ┌────────────────┐
    │ SQLite   │  │ Eastmoney    │  │ Discord        │
    │ DB       │  │ API          │  │ Webhook        │
    └──────────┘  └──────────────┘  └────────────────┘
```

**依赖方向（简化后）**：
- **CLI → Flows/Data → Core**：直接调用，无中间层
- **Flows → Data（具体类）**：直接依赖具体 Repo 类型
- **Core → 无依赖**：只包含数据类和纯函数

**各层职责**：

| 层 | 目录 | 职责 |
|---|---|---|
| 入口层 | `src/cli` | 命令行参数解析 + 流程函数 |
| 流程层 | `src/flows` | 业务逻辑编排（精简后的类） |
| 核心层 | `src/core` | 配置 + 数据模型 + 纯业务规则 |
| 数据层 | `src/data` | 数据库访问 + 外部客户端 |

**命名约定**：
- Repo 类：`TradeRepo`、`NavRepo`、`FundRepo`
- Service 类：`CalendarService`、`EastmoneyNavService`、`LocalNavService`
- Flow 文件：`trade.py`、`dca.py`、`market.py`、`report.py`
- Result 类：`ConfirmResult`、`ReportResult`

## 核心模块

### 数据模型（core/models/）
- `trade.py`：Trade 数据类
- `fund.py`：Fund 数据类
- `dca_plan.py`：DcaPlan 数据类
- `asset_class.py`：AssetClass 枚举
- `policy.py`：SettlementPolicy 数据类

### 业务规则（core/rules/）
- `settlement.py`：确认日期计算（T+N 规则）
- `rebalance.py`：再平衡建议计算
- `precision.py`：金额/份额精度处理

### 数据访问（data/db/）
- `db_helper.py`：DbHelper（数据库初始化）
- `trade_repo.py`：TradeRepo
- `fund_repo.py`：FundRepo
- `nav_repo.py`：NavRepo
- `dca_plan_repo.py`：DcaPlanRepo
- `alloc_config_repo.py`：AllocConfigRepo
- `calendar.py`：CalendarService

### 外部客户端（data/client/）
- `eastmoney.py`：EastmoneyNavService（抓取净值）
- `local_nav.py`：LocalNavService（本地净值查询）
- `discord.py`：DiscordReportService（推送日报）

## NAV 数据流

```
外部抓取（CLI）:
  src/cli/fetch_navs.py
    → EastmoneyNavService.fetch_nav()
    → NavRepo.upsert()
    → SQLite navs 表

本地查询（Flow）:
  src/flows/trade.py: ConfirmTrades
    → LocalNavService.get_nav()
    → NavRepo.get()
    → 返回 Decimal 或 None
```

## 日历与确认

- **策略对象**：`core/models/policy.py` 的 `SettlementPolicy`
- **日历服务**：`data/db/calendar.py` 的 `CalendarService`
- **日历数据**：存储在 `trading_calendar` 表
- **确认规则**：`core/rules/settlement.py` 实现 T+N 计算
- **pricing_date 持久化**：`trades` 表字段（Schema v3）

> 详细规则见 `docs/settlement-rules.md`

## CLI 命令

- `python -m src.cli.confirm --day YYYY-MM-DD`：确认交易
- `python -m src.cli.dca`：执行定投
- `python -m src.cli.report`：生成日报
- `python -m src.cli.fetch_navs --day YYYY-MM-DD`：抓取净值
- `python -m src.cli.fetch_navs_range --from D1 --to D2`：批量抓取

> 详细用法见 `docs/operations-log.md`

## 错误与日志

- 核心层抛异常，入口层捕获并记录
- 统一使用 `core/log.py` 的 `log()` 函数
- SQL trace 由 `ENABLE_SQL_DEBUG` 环境变量控制

## 数据库（SQLite）

- **表**：funds, trades, navs, dca_plans, alloc_config, trading_calendar
- **版本**：Schema v3（meta 表存储）
- **路径**：`data/portfolio.db`（可通过 `DB_PATH` 配置）

> Schema 详见 `docs/sql-schema.md`

## 时间与精度

- **时区**：`Asia/Shanghai`
- **日期格式**：`YYYY-MM-DD`
- **数值类型**：`decimal.Decimal`
- **精度**：金额 2 位，净值/份额 4 位

## 不做/延后（MVP）

- 不做 AI/NLU
- 不做历史导入（当前版本）
- 不做盘中估值
- 不做复杂前端
- 报告与再平衡基于"每日官方净值"
