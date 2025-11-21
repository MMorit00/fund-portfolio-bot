# Portfolio Engine · Claude Code 协作说明

> 你是本项目的 Python 开发助手，只在**开发阶段**使用，不参与线上运行。人类始终是总指挥。（始终使用简体中文回答）

## 项目概述

本仓库是一个个人基金投资管理工具，目标是聚合公募基金持仓、管理定投与 T+1/T+2 确认、计算资产配置与权重、生成文本日报并推送。

> **当前阶段**：纯开发环境，无生产数据；Schema 由 `db_helper.py` 创建，可随时重建，详见 `docs/sql-schema.md`。
> **版本与范围**：见 `docs/roadmap.md`（v0.2/v0.3），禁止实现任何 AI 产品功能，仅做数据准备。

---

## 1. 目录 & 文档导航

```
src/
  core/          # 领域模型与规则（不依赖 adapters）
  usecases/      # 用例（业务流程），依赖 core + ports
  adapters/      # 具体实现（SQLite、HTTP、Discord）
  app/           # 配置、日志、依赖装配、入口
  jobs/          # 定时任务入口
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
- `core`：纯领域逻辑，不依赖外部库实现
- `usecases`：仅依赖 `core` 与 Protocol
- `adapters`：实现具体技术（DB/HTTP/通知）
- `jobs`：只做参数解析与调用，不写业务逻辑

**命名规范**：
- Repository 接口：`{Domain}Repo`（如 `TradeRepo`）
- Service 接口：`{Domain}Protocol`（如 `NavProtocol`）
- UseCase 类：动宾结构（`CreateTrade`、`MakeDailyReport`）
- UseCase 结果：`{名词}Result`（如 `ReportResult`、`ConfirmResult`）

**日志前缀**：`[EastmoneyNav]` `[LocalNav]` `[Discord]` `[Job:xxx]`（详见 `operations-log.md`）

**完成后必跑**：`ruff check --fix .`

---

## 4. 配置与环境变量

敏感信息和可变参数通过环境变量 / `.env` 提供，**禁止写死在代码中**。

**典型配置**（由 `src/app/config.py` 读取，完整列表见该文件及 `docs/operations-log.md`）：
- `DISCORD_WEBHOOK_URL` / `DB_PATH` / `ENABLE_SQL_DEBUG`

**新增配置项**：先在文档写明用途 → 再在 `app/config.py` 集中读取 → **不直接用** `os.getenv`

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
