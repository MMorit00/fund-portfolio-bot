# 架构说明

> 快速查阅。详细说明见 CLAUDE.md。

## 项目定位

个人基金投资的命令式工具，Python 实现，职责分明。

## 目录结构

```
src/
  cli/          # 命令行入口
  flows/        # 业务流程函数（@dependency 装饰器）
  core/         # 配置 + 模型 + 规则 + 依赖注入
    ├─ models/  #   数据类（Trade, Fund, DcaPlan）
    └─ rules/   #   纯业务规则
  data/         # 数据访问层
    ├─ db/      #   数据库 Repo
    └─ client/  #   外部客户端（FundDataClient, DiscordClient）
```

## 分层架构

```
CLI（参数解析）
    ↓
Flows（业务函数，@dependency 自动注入）
    ↓
Core（模型 + 规则） + Data（数据访问）
    ↓
SQLite / Eastmoney API / Discord Webhook
```

## 各层职责

| 层 | 职责 |
|----|------|
| **cli/** | 参数解析 + Flow 调用 + 输出格式化 |
| **flows/** | 业务逻辑编排（纯函数，参数通过 @dependency 自动注入） |
| **core/** | 数据模型 + 业务规则 + DI 容器 |
| **data/db/** | SQLite 数据访问（TradeRepo, NavRepo 等） |
| **data/client/** | 外部 I/O（HTTP 请求、Webhook 推送） |

## 核心模块

**core/models/**：Trade, Fund, DcaPlan, DcaInferResult, FundDcaFacts 等

**core/rules/**：settlement（T+N）, rebalance（再平衡）, precision（精度）

**core/container.py**：依赖工厂函数（get_trade_repo(), get_nav_service() 等）

**data/db/**：TradeRepo, NavRepo, FundRepo, DcaPlanRepo, CalendarService, FundRestrictionRepo

**data/client/**：FundDataClient（抓取净值、查询限额），LocalNavService（本地查询），DiscordClient（推送）

## 命名约定

- **Repo**：TradeRepo, NavRepo（数据库访问）
- **Client**：FundDataClient, DiscordClient（纯 I/O）
- **Service**：CalendarService, LocalNavService（业务逻辑）
- **Flow 函数**：create_trade(), confirm_trades(), draft_dca_plans()
- **Result 类**：ConfirmResult, FetchNavsResult, BackfillResult
- **Draft/Facts/Check**：DcaPlanDraft, FundDcaFacts, DcaTradeCheck（规则 vs AI 分工）

## 关键约束

✅ **分层**：cli → flows → core/data，反向无依赖
✅ **类型注解**：全覆盖，Decimal 用于金额
✅ **依赖注入**：@dependency 自动注入，不手动实例化
✅ **规则 vs AI**：规则层输出事实（日期、金额偏差、限额事实），AI 做语义判断

> 详见 CLAUDE.md "算法 vs AI 分工"节
