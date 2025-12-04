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

## 分层架构（v0.3.1 简化版 + 依赖注入）

```
┌─────────────────────────────────────────────────────────────┐
│                   src/cli（命令行入口）                       │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  CLI: 参数解析 + 一行调用 Flow 函数                    │  │
│  │  - confirm.py:  confirm_trades(today=day)            │  │
│  │  - dca.py:      run_daily_dca(today=today)           │  │
│  │  - report.py:   make_daily_report(mode="market")     │  │
│  │  无需手动实例化依赖（装饰器自动注入）                   │  │
│  └───────────────────────────────────────────────────────┘  │
└────────────┬────────────────────────────────────────────────┘
             │
             │ 调用（依赖自动注入）
             ▼
┌─────────────────────────────────────────────────────────────┐
│  src/flows（业务流程函数，使用 @dependency 装饰器）          │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │  纯函数（带自动依赖注入）                                │ │
│ │  - create_trade()        → Trade                       │ │
│ │  - confirm_trades()      → ConfirmResult               │ │
│ │  - run_daily_dca()       → int                         │ │
│ │  - make_daily_report()   → str                         │ │
│ │  - fetch_navs()          → FetchNavsResult             │ │
│ │  返回：Result dataclass 或基础类型                       │ │
│ └─────────────────────────────────────────────────────────┘ │
└────────────┬────────────────────────────┬───────────────────┘
             │                            │
             │ 使用模型 + 规则              │ 通过装饰器注入
             ▼                            ▼
┌──────────────────────────────┐    ┌──────────────────────────┐
│ src/core（核心逻辑 + DI）     │    │  src/data（数据访问）      │
│ ┌──────────────────────────┐ │    │ ┌──────────────────────┐ │
│ │ models/                  │ │    │ │ db/                  │ │
│ │   Trade, Fund, DcaPlan   │ │    │ │   TradeRepo          │ │
│ │ rules/                   │ │    │ │   NavRepo            │ │
│ │   settlement, rebalance  │ │    │ │   CalendarService    │ │
│ │ dependency.py            │ │    │ ├──────────────────────┤ │
│ │   @dependency 装饰器     │ │    │ │ client/              │ │
│ │   @register 装饰器       │ │    │ │   EastmoneyClient    │ │
│ │ container.py             │ │    │ │   LocalNavService    │ │
│ │   依赖工厂函数集合        │ │    │ │   DiscordClient      │ │
│ │   get_trade_repo() 等    │ │    │ └──────────────────────┘ │
│ │ config.py, log.py        │ │    └────────────┬─────────────┘
│ └──────────────────────────┘ │                 │
└──────────────────────────────┘                 │
             ▲                                   │
             └───────────────────────────────────┘
                      工厂函数创建实例

                         外部系统
    ┌──────────┐  ┌──────────────┐  ┌────────────────┐
    │ SQLite   │  │ Eastmoney    │  │ Discord        │
    │ DB       │  │ API          │  │ Webhook        │
    └──────────┘  └──────────────┘  └────────────────┘
```

**依赖注入机制（v0.3.1）**：
```
1. 注册阶段（src/core/container.py）:
   @register("trade_repo")
   def get_trade_repo() -> TradeRepo:
       conn = get_db_connection()
       calendar = get_calendar_service()
       return TradeRepo(conn, calendar)

2. 声明阶段（src/flows/trade.py）:
   @dependency
   def confirm_trades(
       *,
       today: date,
       trade_repo: TradeRepo | None = None,  # 自动注入
       nav_service: LocalNavService | None = None,  # 自动注入
   ) -> ConfirmResult:
       # 直接使用，无需手动检查 None
       to_confirm = trade_repo.list_pending(today)
       ...

3. 调用阶段（src/cli/confirm.py）:
   result = confirm_trades(today=day)  # 依赖自动创建并注入
```

**依赖方向**：
- **CLI → Flows**：直接调用函数，参数传递业务数据
- **Flows → Data**：通过 `@dependency` 装饰器自动注入
- **Core/Container → Data**：工厂函数创建 Data 层实例
- **Core/Models + Rules → 无依赖**：纯数据类和纯函数

**各层职责**：

| 层 | 目录 | 职责 |
|---|---|---|
| 入口层 | `src/cli` | 命令行参数解析 + Flow 函数调用 + 结果格式化输出 |
| 流程层 | `src/flows` | 业务逻辑编排（纯函数 + @dependency 装饰器） |
| 核心层 | `src/core` | 配置 + 模型 + 规则 + 依赖注入（DI） |
| 数据层 | `src/data` | 数据库访问 + 外部客户端 |

**CLI 层标准结构**（v0.4.2+）：

```python
def _parse_args() -> argparse.Namespace: ...  # 参数解析
def _format_*(...) -> None: ...                # 格式化输出（可选）
def _do_*(...) -> int: ...                     # 执行命令（返回码：0/4/5）
def main() -> int: ...                         # 路由入口
```

规范：职责分离 + 数字注释（`# 1.` `# 2.`）+ 统一 `log()` + 标准返回码

**命名约定**：
- Repo 类：`TradeRepo`、`NavRepo`、`FundRepo`（数据库访问）
- Client 类：`EastmoneyClient`、`DiscordClient`（纯 I/O，无业务逻辑）
- Service 类：`CalendarService`、`LocalNavService`（封装业务逻辑）
- Flow 函数：`create_trade()`、`confirm_trades()`、`make_daily_report()`
- Result 类：`ConfirmResult`、`ReportResult`、`FetchNavsResult`
- 依赖注入：`@dependency`、`@register`

**Client vs Service 区分**：
- **Client**：只负责 I/O（HTTP 请求、Webhook 推送），不含业务逻辑
- **Service**：在数据基础上封装业务逻辑（如 LocalNavService 提供运行时 NAV 查询接口）

## 核心模块

### 数据模型（core/models/）
- `trade.py`：Trade 数据类
- `fund.py`：Fund 数据类
- `dca_plan.py`：DcaPlan 数据类
- `asset_class.py`：AssetClass 枚举
- `policy.py`：SettlementPolicy 数据类（结算日历策略）

### 业务规则（core/rules/）
- `settlement.py`：确认日期计算（T+N 规则）
- `rebalance.py`：再平衡建议计算
- `precision.py`：金额/份额精度处理

### 依赖注入（core/）
- `dependency.py`：依赖注入装饰器
  - `@register(name)`：注册工厂函数到容器
  - `@dependency`：自动注入函数参数
  - `get_registered_deps()`：查看已注册依赖（调试用）
- `container.py`：依赖工厂集合
  - `get_db_connection()`：数据库连接（单例）
  - `get_trade_repo()`：交易仓储工厂
  - `get_nav_service()`：净值服务工厂
  - 等 9 个依赖工厂函数

### 数据访问（data/db/）
- `db_helper.py`：DbHelper（数据库初始化）
- `trade_repo.py`：TradeRepo
- `fund_repo.py`：FundRepo
- `nav_repo.py`：NavRepo
- `dca_plan_repo.py`：DcaPlanRepo
- `alloc_config_repo.py`：AllocConfigRepo
- `calendar.py`：CalendarService

### 外部客户端（data/client/）
- `eastmoney.py`：EastmoneyClient（东方财富 API 客户端：抓取净值、搜索基金）
- `local_nav.py`：LocalNavService（本地净值查询服务）
- `discord.py`：DiscordClient（Discord Webhook 客户端：推送消息）

## NAV 数据流

```
外部抓取（CLI → Flow）:
  src/cli/fetch_navs.py: main()
    → src/flows/market.py: fetch_navs(day=day)
      → EastmoneyClient.get_nav()  # 自动注入
      → NavRepo.upsert()           # 自动注入
      → SQLite navs 表

本地查询（Flow → Service）:
  src/flows/trade.py: confirm_trades()
    → LocalNavService.get_nav()  # 自动注入
      → NavRepo.get()
      → 返回 Decimal 或 None
```

## 日历与确认

- **结算日历策略对象**：`core/models/policy.py` 的 `SettlementPolicy`
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

## ActionLog 角色 & strategy 字段

### 设计定位

项目数据分为两层：

- **真相层**（trades/navs/dca_plans/calendar）：底层事实数据，记录"钱怎么动的、持仓是多少、规则是什么"（可严格复算）
- **故事层**（action_log）：行为时间线，记录"谁在什么时候对什么做了什么、出于什么意图、属于什么策略"（供人类/AI理解）

**ActionLog 的作用**：
- 为 AI/人类提供结构化的行为数据（时间序列 + 标签）
- 区分行为的策略语境（定投 vs 再平衡 vs 普通买卖）
- 记录操作意图和人话备注，便于后续分析

### strategy 字段（v0.4.3）

**定义**：
```python
Strategy = Literal["dca", "rebalance", "none"]
```

- `dca`：定投相关行为（含跳过定投）
- `rebalance`：再平衡相关行为
- `none`：普通手动买卖、历史导入等

**使用场景**：

| 行为来源 | strategy 取值 |
|---------|--------------|
| 手动买入/卖出 | `none` |
| DCA 自动执行 | 不记录 ActionLog（系统行为） |
| DCA 跳过 | `dca` |
| 历史账单导入 | `none`（初始值，可后续回填） |
| 再平衡执行 | `rebalance`（未来） |

**字段特性**：
- 属于"解释字段"：允许后续回填/修正，不改变事实层数据
- 与"事实字段"（action/actor/source/acted_at/trade_id）区分：事实字段只能 append-only

### 未来扩展（TODO）

当需要"DCA 执行率统计"或"导入回填 DCA 归属"时，考虑启用以下字段：

**ActionLog 深度字段**：
- `is_dca_execution: bool | None` - 是否为 DCA 执行
- `dca_plan_key: str | None` - 关联的定投计划标识
- `dca_tag_source: "auto_run" | "import_infer" | "manual" | None` - DCA 归属来源

**Trade 层 DCA 归属**：
- `dca_plan_key: str | None` - 交易归属的定投计划
- `dca_tag_source` - 归属来源标记

**实现时机**：
- 需要执行率报表（实际执行数 / 计划执行数）
- 需要导入回填（将历史交易标记为 DCA）
- 需要 DCA 归因分析

> 详细设计见 `docs/sql-schema.md` 的"ActionLog v2 演进规划"章节

### 算法 vs AI 分工（事实 vs 语义）

本项目默认的分工原则是：

- **规则/算法层负责“事实”**  
  - 只计算、存储可被严格验证的结构化信号，例如：  
    - 这笔交易的日期是否落在某个 DCA 频率轨道上（`date_matches_plan`）；  
    - 实际金额相对计划金额的偏离比例（`amount_deviation`）；  
    - 当日是否存在限额公告、限额金额是多少；  
  - 这些事实可以从 trades/navs/trading_calendar/fund_restrictions 中**随时重算**。

- **AI 层负责“语义”**  
  - 在看到上述事实 + 行为时间线后，给出高层判断与解释，例如：  
    - 这笔是否算一次定投执行（`is_dca_execution`）；  
    - 执行状态是正常 / 受限 / 主动调整；  
    - 金额变化更像“平台限额”还是“用户策略调整”；  
  - AI 的输出只写入 ActionLog 等“解释字段”，**不直接改动真相层（trades/navs 等）**。

- **演进方向**  
  - 当前实现中，DCA 推断/回填仍包含少量“语义判断”（如用金额窗口直接判断是否属于 DCA），这是可工作的 v0.x 版本启发式；  
  - 中长期目标是：规则层只负责算出“日期节奏、金额偏离、是否有公告”等事实特征，回填只写入“计划归属”；  
  - 最终由 AI 在这些事实之上做更细腻的解释与归因（限额 vs 策略调整 vs 情绪化加仓等）。

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
