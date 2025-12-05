# Portfolio Engine · Claude Code 协作说明

> 你是本项目的 Python 开发助手，只在**开发阶段**使用，不参与线上运行。人类始终是总指挥。（始终使用简体中文回答）

## 项目概述

本仓库是一个个人基金投资管理工具，目标是聚合公募基金持仓、管理定投与 T+1/T+2 确认、计算资产配置与权重、生成文本日报并推送。

> **当前版本**：v0.4.2+（业务闭环 100% 完整，生产可用）
> **Schema 管理**：开发阶段，由 `db_helper.py` 创建（SCHEMA_VERSION = 8），可随时重建，详见 `docs/sql-schema.md`
> **版本规划**：见 `docs/roadmap.md`，禁止实现任何 AI 产品功能，仅做数据准备

### 算法 vs AI 分工（核心设计原则）

本项目是 **AI 驱动** 的投资管理工具，核心设计原则是 **算法处理事实，AI 处理语义**：

```
┌─────────────────────────────────────────────────────────────┐
│                        分工边界                              │
├──────────────────────┬──────────────────────────────────────┤
│       规则/算法       │                 AI                   │
├──────────────────────┼──────────────────────────────────────┤
│ • 日期匹配计算        │ • 判断是否归属定投                    │
│ • 金额偏差率          │ • 解释偏差原因（限额/调整）            │
│ • 限购公告查询        │ • 综合多因素做语义判断                 │
│ • 交易模式统计        │ • 向用户提问澄清                      │
├──────────────────────┼──────────────────────────────────────┤
│     可计算/可验证      │         需要理解/判断                 │
└──────────────────────┴──────────────────────────────────────┘
```

**交互流程**：规则层输出事实 → AI 层做语义判断 → 用户确认修改

**核心约束**：规则只输出**事实**，AI 只做**解释**，修改需**用户确认**

> 详细说明见 `docs/architecture.md` 的"算法 vs AI 分工"节

### 环境说明

**⚠️ 重要**：本项目使用 **uv** 管理 Python 依赖。

所有 CLI 命令必须使用 `uv run` 前缀：

```bash
# ✅ 正确
uv run python -m src.cli.fund list
uv run python -m src.cli.history_import --csv data/alipay.csv --mode apply

# ❌ 错误（会报 ModuleNotFoundError）
python -m src.cli.fund list
```

**原因**：uv 使用独立虚拟环境（`.venv/`），直接运行 `python` 无法访问依赖。

**测试命令时请务必加上 `uv run` 前缀。**

---

## 1. 目录 & 文档导航

```
src/
  cli/           # 命令行入口（原 jobs/）
  flows/         # 业务流程（原 usecases/）
  core/          # 核心逻辑
    ├─ models/   #   领域数据类（Trade, Fund 等）
    └─ rules/    #   纯业务规则（settlement, rebalance 等）
  data/          # 数据访问层（原 adapters/）
    ├─ db/       #   数据库 Repo
    └─ client/   #   外部客户端（HTTP、Discord 等）
docs/
  architecture.md      # 架构与分层（含 ASCII 图）
  settlement-rules.md  # 业务规则权威
  operations-log.md    # 运维操作手册
  coding-log.md        # 开发变更记录
  roadmap.md           # 版本规划
  sql-schema.md        # Schema 说明
```

**开始任务前必读**：`architecture.md` / `roadmap.md` / 最近的 `coding-log.md`
**编码规范**：在本文件第 3 节 + `.claude/skills/`

---

## 2. 工作流程（核心原则）

> 详细流程见 `.claude/skills/dev-workflow/SKILL.md`

1. **不直接写代码**，先读文档和代码
2. **先给计划**，等确认后再编码
3. **默认只改 1-3 个文件**
4. **遵守分层**：`core` 不依赖 `adapters`
5. **编码后运行** `ruff check --fix .`

**文档同步**：
- 架构/行为决定 → 更新 `docs/coding-log.md`
- Schema/涉及分层架构变更 → **必须先问**

**文档清理**（我会主动提醒）：
- 发现过时说明/与代码不一致/引用已删除模块时提醒你
- 历史决策统一记在 `coding-log.md`，不在其他文档堆"草稿"

**图表化原则**：
- 修改/新增文档时，适合用图表的地方优先用 ASCII 图（数据流/状态机/调用链/文件树）
- 代码总结时主动用图表展示变更（详见 `.claude/skills/code-style/SKILL.md`）

---

## 3. 编码规范（核心约束）

> 完整规范见 `.claude/skills/code-style/SKILL.md` 和 `.claude/skills/architecture/SKILL.md`

**类型与精度**：
- 类型注解必须全；金额/净值/份额用 `Decimal`（金额 2 位、净值/份额 4 位小数）
- Docstring 用中文

**分层约束**：
- `core`：核心逻辑 + 依赖注入（models + rules + dependency + container + config/log）
- `flows`：业务流程函数（纯函数 + `@dependency` 装饰器），依赖 core
- `data`：数据访问，依赖 core（DB Repo + 外部客户端）
- `cli`：只做参数解析与 Flow 函数调用，不写业务逻辑

**命名规范**：
- Repo 类：`TradeRepo`、`NavRepo`（直接具体类名）
- Service 类：`CalendarService`、`EastmoneyNavService`
- Flow 函数：小写蛇形（`create_trade()`、`confirm_trades()`、`make_daily_report()`）
- Result 类：`{名词}Result`（如 `ReportResult`、`ConfirmResult`）
- 依赖注入：`@dependency`、`@register`

**日志前缀**：`[EastmoneyNav]` `[LocalNav]` `[Discord]` `[Job:xxx]`（详见 `operations-log.md`）

**完成后必跑**：`ruff check --fix .`

### 3.x 领域命名规范：DCA & AI 分工（Domain Naming）

本项目是 **AI 驱动** 的投资工具，在 DCA、历史扫描、AI 分析相关模块中，严格遵循 **"规则算事实 (Facts)，AI 做解释 (Semantic)"** 的分工原则。

#### 3.x.1 规则层数据模型：Facts / Check / Flag / Draft / Report

规则层只负责输出可重算、无歧义的结构化数据，严禁直接生成主观结论。

- **事实快照 (Facts)**
  - **后缀：** `*Facts`
  - **定义：** 某一对象在特定时间段内的客观数据聚合（如交易日期、金额分布、间隔统计）。
  - **角色：** 作为 **Context** 提供给 AI 或上层逻辑。
  - **示例：** `FundDcaFacts`

- **检查结果 (Check)**
  - **后缀：** `*Check`
  - **定义：** 单条数据针对特定规则的验证结果（是否命中 + 差异数值 + 简要说明）。
  - **示例：** `DcaTradeCheck`

- **标记点 (Flag)**
  - **后缀：** `*Flag`
  - **定义：** 规则识别出的"值得注意"的数据点（如异常金额、中断），但不下定性结论。
  - **示例：** `TradeFlag`

- **待定草稿 (Draft)**
  - **后缀：** `*Draft`
  - **定义：** 生成的建议方案（如定投计划草稿），永远不直接对应 DB 表，只是内存结构。
  - **示例：** `PlanDraft`、`DcaPlanCandidate`

- **汇总报告 (Report/Result)**
  - **后缀：** `*Report`（CLI/外部展示）或 `*Result`（内部中间结果）
  - **定义：** 面向 CLI 展示或 AI 输入的聚合统计结果。
  - **示例：** `BackfillResult`（内部）、`ScanReport`（外部展示）

#### 3.x.2 Flow 函数动作 (Verbs)

- **`build_*_facts` / `collect_*`**
  - **含义：** 纯计算/聚合，返回 `*Facts` 对象。
  - **约束：** 只读，无副作用。
  - **示例：** `build_dca_facts_for_batch()`

- **`scan_*`**
  - **含义：** 扫描历史数据，输出 `*Report` (包含 Checks/Flags)。
  - **约束：** **只读，无副作用（Idempotent）**。严禁修改 trades/action_log 表。可随意调用，无安全隐患。

- **`draft_*`**
  - **含义：** 生成建议方案（Drafts）。
  - **约束：** 返回 `*Draft` 对象，不直接入库。

- **`backfill_*`**
  - **含义：** 执行回填逻辑，将归属关系或标签写入数据库。
  - **约束：** **写操作**。会修改 Truth Layer (trades.dca_plan_key, action_log 等)。需谨慎调用。

#### 3.x.3 AI 层（预留）：Insight / Explanation / Label

AI 层基于规则层提供的 Context 生成语义解释，仅写入解释性字段，不修改核心事实。

- **后缀：** `*Insight` (洞察), `*Explanation` (解释), `*Label` (语义标签)
- **原则：** AI 的输出是对 Facts 的注释，而非 Facts 本身。不会修改 Truth Layer。

---

## 4. 配置与环境变量

敏感信息和可变参数通过环境变量 / `.env` 提供，**禁止写死在代码中**。

**典型配置**（由 `src/core/config.py` 读取，完整列表见该文件及 `docs/operations-log.md`）：
- `DISCORD_WEBHOOK_URL` / `DB_PATH` / `ENABLE_SQL_DEBUG`

**新增配置项**：先在文档写明用途 → 再在 `core/config.py` 集中读取 → **不直接用** `os.getenv`

---

## 5. 当前版本行为（只做跳转）

- **展示日 / NAV 严格口径 / 再平衡规则** → `docs/settlement-rules.md`
- **日报与抓取 Job 用法** → `docs/operations-log.md`
- **版本目标与完成状态** → `docs/roadmap.md`

---

## 6. 禁止事项（以 roadmap 为准）

当前阶段明确不做：
- 历史导入（只允许预留 TODO）
- 盘中估值作为核心口径（只允许未来做"附加字段"）
- 任意 AI 产品功能（仅做数据准备：标签/快照/Outcome）
- 复杂错误处理/审计框架
- 破坏性操作（删除顶层目录、重建 DB 结构等）

---

## 7. 提问原则

当不确定时，**先问**，例如：
- "当前任务是否允许修改 schema？"
- "这个 TODO 是现在实现，还是留到未来版本？"
- "是否可以新增第三方依赖 X？"

**涉及 schema/DB 或分层架构变更时，必须先问**。

---

## 8. 工具使用策略（极简版）

> 详细说明见各工具文档，这里只列核心原则

**基础优先**：
- 简单查询/修改 → `Grep` / `Glob` / `Read` / `Edit`
- 代码探索 → `Explore` subagent（只理解结构，不写代码）

**按需升级**：
- 复杂设计/重构 → `Sequential-Thinking` MCP（先推理方案）
- 全局搜索 → `Code-Index` MCP（大范围/复杂模式）
- 外部资料 → `Exa` MCP（视环境而定）

**工具调用优先级**：
1. 简单 → Grep/Glob/Read/Edit
2. 探索 → Explore subagent
3. 全局搜索 → Code-Index MCP
4. 复杂推演 → Sequential-Thinking MCP
5. 外部调研 → Exa MCP

---

感谢配合！
