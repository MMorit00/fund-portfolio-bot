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
  ai/           # AI 分析层（v0.5.0 规划）
    ├─ client/  #   LLM API 客户端
    ├─ tools/   #   AI 可调用的工具函数
    └─ prompts/ #   系统提示词模板
```

## 分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│  CLI（参数解析）                                                 │
│    ├─ 业务命令：trade, dca, report, bill...                     │
│    └─ AI 命令：ai chat（自然语言交互）                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Flows（业务函数）              AI（分析层）                      │
│    ├─ 交易管理                   ├─ 单 AI + Tools 模式           │
│    ├─ 定投执行                   ├─ 只读，给建议不执行            │
│    └─ 报告生成                   └─ 调用 Tools 获取数据           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Core（模型 + 规则） + Data（数据访问）                           │
│    ActionLog ← AI 的唯一信息源                                   │
│    trades, navs, fund_restrictions ← 通过 Tools 拼装给 AI       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  SQLite / Eastmoney API / Discord Webhook / LLM API（豆包等）   │
└─────────────────────────────────────────────────────────────────┘
```

## 各层职责

| 层 | 职责 |
|----|------|
| **cli/** | 参数解析 + Flow 调用 + 输出格式化 |
| **flows/** | 业务逻辑编排（纯函数，参数通过 @dependency 自动注入） |
| **core/** | 数据模型 + 业务规则 + DI 容器 |
| **data/db/** | SQLite 数据访问（TradeRepo, NavRepo 等） |
| **data/client/** | 外部 I/O（HTTP 请求、Webhook 推送） |
| **ai/** | AI 分析层（v0.5.0），只读分析，给建议不执行 |

## 核心模块

**core/models/**：Trade, Fund, DcaPlan, FundDcaFacts 等

**core/rules/**：settlement（T+N）, rebalance（再平衡）, precision（精度）

**core/container.py**：依赖工厂函数（get_trade_repo(), get_nav_service() 等）

**data/db/**：TradeRepo, NavRepo, FundRepo, DcaPlanRepo, CalendarService, FundRestrictionRepo

**data/client/**：FundDataClient（抓取净值、查询限额），LocalNavService（本地查询），DiscordClient（推送）

## 命名约定

- **Repo**：TradeRepo, NavRepo（数据库访问）
- **Client**：FundDataClient, DiscordClient（纯 I/O）
- **Service**：CalendarService, LocalNavService（业务逻辑）
- **Flow 函数**：create_trade(), confirm_trades(), build_fund_dca_facts()
- **Result 类**：ConfirmResult, FetchNavsResult, BackfillResult
- **Facts/Check**：FundDcaFacts, DcaTradeCheck（规则 vs AI 分工）

## 关键约束

✅ **分层**：cli → flows → core/data，反向无依赖
✅ **类型注解**：全覆盖，Decimal 用于金额
✅ **依赖注入**：@dependency 自动注入，不手动实例化
✅ **规则 vs AI**：规则层输出事实（日期、金额偏差、限额事实），AI 做语义判断

> 详见 CLAUDE.md "算法 vs AI 分工"节

---

## AI 层设计（v0.5.0）

### 架构模式：单 AI + Tools

```
用户（自然语言）
    ↓
AI（豆包/其他模型）
    ↓
Tools（我们写的函数）
    ↓
ActionLog + trades + fund_restrictions（数据层）
```

### 核心原则

1. **ActionLog 是 AI 的唯一信息源**
   - AI 不直接访问 trades/navs
   - 通过 Tools 获取拼装后的数据（内存中 JOIN）

2. **不为 AI 改 Schema**
   - 需要金额等信息时，代码层拼装
   - 保持数据层干净

3. **AI 边界：给建议，不执行**
   - ✅ 分析行为模式、解释异常、给建议
   - ❌ 不执行任何写操作

4. **Tools 帮 AI 计算**
   - AI 不擅长计算，我们写函数
   - 查询类、计算类、上下文类

### Tools 分类

| 类型 | 示例 | 说明 |
|------|------|------|
| 查询 | `get_actions_by_period()` | 按时间/基金/策略查询 ActionLog |
| 详情 | `get_action_detail()` | 获取单条 + 关联交易（含金额） |
| 计算 | `calc_dca_execution_rate()` | 执行率、行为统计、异常检测 |
| 上下文 | `get_restriction_context()` | 限额事实、历史对比 |

### 数据流

```
导入阶段（临时 AI）：
  CSV → 算法 → BillFacts → AI 判断定投归属 → 回填 ActionLog.strategy

分析阶段（常驻 AI）：
  用户提问 → AI → 调用 Tools → 分析 → 给出建议
```

> 详见 `docs/roadmap.md` v0.5.0 章节
