# Portfolio Engine · Claude Code 协作说明

> 你是本项目的 Python 开发助手，只在**开发阶段**使用，不参与线上运行。人类始终是总指挥。（始终使用简体中文回答）

## 项目概述

本仓库是一个个人基金投资管理工具，目标是：

- 聚合公募基金持仓
- 管理定投与 T+1/T+2 确认
- 计算资产配置与权重
- 生成文本日报并通过 Discord Webhook 推送

> ⚠️ **重要**：当前阶段（参见 `docs/roadmap.md` v0.2/v0.3）**不做任何 AI 产品功能**，你只作为写代码/改代码的助手，但可以按 roadmap 要求为未来 AI 预留数据结构（标签、视图、快照）。

> 🔧 **开发阶段说明**：
> - 本项目处于**纯开发阶段**，无生产环境，无真实用户数据
> - 数据库是**测试数据库**，可随时通过 `SEED_RESET=1 python -m scripts.dev_seed_db` 重建
> - Schema 变更**无需迁移文档**，直接修改 `db_helper.py` 后重建即可
> - 历史决策记录在 `docs/coding-log.md`，无需维护详细的迁移步骤

---

## 1. 代码结构概要

项目采用标准 `src` 布局：

```
src/
  core/          # 领域模型与规则（不依赖 adapters）
  usecases/      # 用例（业务流程），依赖 core + ports
  adapters/      # 具体实现（SQLite、HTTP 抓净值、Discord 推送）
  app/           # 配置、日志、依赖装配、入口
  jobs/          # 定时任务入口（fetch_navs / run_dca / confirm_trades / daily_report）

docs/
  architecture.md    # 架构与分层说明
  python-style.md    # Python 编码规范（含 import 顺序）
  operations-log.md  # 环境与运维记录（含日志规范）
  coding-log.md      # 开发变更记录
  roadmap.md         # Roadmap 与大 TODO
  tooling.md         # 工具链配置（ruff / mypy）

data/
  portfolio.db       # SQLite 数据文件（实际创建后才存在）

scripts/
  backup_db.sh       # 手动 DB 备份脚本
```

在开始任何任务前，你应该优先阅读：

- `docs/architecture.md`（架构与分层）
- `docs/python-style.md`（编码规范，含类型、import、docstring）
- `docs/roadmap.md`（当前版本目标）
- 最近几条 `docs/coding-log.md`（最新变更）
- `docs/tooling.md`（工具链使用，按需查阅）


## 2. Python 编码规范（摘要）

> 基础编码规范详见 `.claude/skills/code-style/SKILL.md` 和 `docs/python-style.md`。
> 这里只列出最关键的提醒。

**核心要点**：
- 类型注解必须全；金额/净值用 `Decimal`；Docstring 用中文
- 代码组织：入口在上、工具在下；公开在上、私有在下
- 编码完成后运行 `ruff check --fix .`

**日志前缀规范**（见 `docs/operations-log.md`）：
- `[EastmoneyNav]`、`[LocalNav]`、`[Discord]`、`[Job:xxx]` 等

---

## 3. 配置与环境变量

敏感信息和可变参数通过环境变量 / `.env` 提供，**禁止写死在代码中**。

典型配置（由 `src/app/config.py` 读取）：

- `DISCORD_WEBHOOK_URL`：日报推送地址
- `DB_PATH`：SQLite 路径（默认 `data/portfolio.db`）
- `NAV_DATA_SOURCE`：净值数据源（默认 `eastmoney`）
- `TIMEZONE`：时区（默认 Asia/Shanghai 或与你的设定一致）
- `ENABLE_SQL_DEBUG`：是否启用 SQL trace 打印（可选）

如果你需要新增配置项，必须：

1. 先在 `docs/architecture.md` 或 `docs/operations-log.md` 里写明用途
2. 再在 `app/config.py` 中集中读取
3. **不要**在业务代码中直接调用 `os.getenv`（统一走 config 层）

---

## 4. 工作流程（非常重要）

> 详细流程见 `.claude/skills/dev-workflow/SKILL.md`。
> 每次任务必须遵守：先读项目 → 给设计 → 限制改动（1-3 文件）→ 编码 → 文档同步。

**核心原则**：
1. 不要直接写代码，先读文档和代码
2. 先给计划，等确认后再编码
3. 默认只改 1-3 个文件
4. 遵守分层：`core` 不依赖 `adapters`
5. 编码后运行 `ruff check --fix .`

**文档同步**：
- 架构/行为决定 → 更新 `docs/coding-log.md`
- 必要时更新 `docs/architecture.md` 或 `docs/roadmap.md`


**文档清理原则**（开发阶段简化版）：
- **主动提醒时机**（我会在发现时提醒你）：
  - ❌ 文档中出现"设计草稿""临时方案"超过 3 个月
  - ❌ 与当前代码实现不一致的说明
  - ❌ 引用已删除的代码/模块/配置
- **清理优先级**：
  - 🔴 高：过时的操作步骤（已被新方法替代）
  - 🟡 中：重复内容（已被其他文档覆盖）
  - 🟢 低：历史决策记录（保留在 coding-log）

**文档图表化原则**：
- 当修改或新增文档时，如遇到适合用图表表达的内容，**优先使用 ASCII 图 / Text 图**来增强可读性
- **修改代码后做总结时，也要主动思考是否需要用图表**来让变更更清晰（见下方"代码总结图表化"）
- 适合场景举例：
  - **数据流图**：用箭头和方框展示数据在模块间的流动（如 NAV 数据流）
  - **状态机**：展示交易确认的状态转换（pending → confirmed/delayed）
  - **时序图**：说明多步骤流程的执行顺序（如每日调度顺序）
  - **树形结构**：展示目录层级、依赖关系、决策树
  - **表格对比**：用 Markdown 表格展示字段含义、命名规范、版本差异
  - **调用链路**：展示函数/模块之间的调用关系与依赖方向
- 工具选择：
  - 简单流程：用 `→` `├─` `└─` 等 ASCII 字符绘制
  - 复杂架构：用 Markdown 代码块 + 缩进表达层次关系
  - 对比说明：用 Markdown 表格（`|`分隔）
- 示例参考：`docs/architecture/architecture-ascii.md`（已有的架构图）

**代码总结图表化**（完成代码修改后）：
- 在总结代码变更时，**优先用图表展示关键变化**，而非纯文字罗列
- 典型场景：
  - **文件修改树**：展示修改了哪些文件及其层级关系
    ```
    src/
    ├── core/
    │   ├── protocols.py          [新增] 集中定义所有 Protocol
    │   └── trading/
    │       └── settlement.py     [修改] 确认规则升级为 v0.2
    └── usecases/
        └── trading/
            └── confirm_pending.py [修改] 使用定价日 NAV
    ```
  - **调用链路变化**：展示重构前后的调用关系
    ```
    # 重构前
    Job → UseCase → SqliteTradeRepo (直接依赖具体实现)

    # 重构后
    Job → UseCase → TradeRepo (Protocol) ← SqliteTradeRepo (注入)
    ```
  - **数据流变化**：展示新增或修改的数据处理路径
    ```
    HTTP (Eastmoney)
      ↓
    EastmoneyNavService.get_nav()
      ↓
    NavRepo.upsert() → navs 表
      ↓
    LocalNavService.get_nav() ← ConfirmPendingTrades
    ```
  - **影响范围矩阵**：用表格总结改动的影响面
    | 层级 | 修改文件数 | 新增/删除 | 影响的 UseCase |
    |------|-----------|----------|----------------|
    | core | 2 修改, 1 新增 | +120 / -0 | 所有交易确认相关 |
    | usecases | 3 修改 | +45 / -30 | ConfirmPendingTrades, CreateTrade |
    | adapters | 1 修改 | +10 / -5 | SqliteTradeRepo |
  - **版本对比**：展示 schema/API/行为的版本差异
    ```
    v0.1: confirm_date = trade_date + lag (简单顺延周末)
    v0.2: pricing_date = next_trading_day(trade_date)
          confirm_date = next_trading_day(pricing_date, offset=lag)
    ```
- **何时使用**：
  - 修改超过 3 个文件时，用文件树展示影响范围
  - 重构模块依赖时，用调用链路图对比变化
  - 修改数据流时，用箭头图展示新的处理路径
  - 功能升级时，用版本对比说明行为变化

---

## 8. 近期实现提示（v0.2 严格版：展示日与抓取）

- 日报/状态视图默认展示日 = 上一交易日（当前按“上一工作日”近似）。
  - CLI：`status --mode {market,shares} --as-of YYYY-MM-DD`（未提供 `--as-of` 时默认上一交易日）
  - Job：`daily_report --mode {market,shares} --as-of YYYY-MM-DD`
  - 严格不回退：对选定展示日，仅使用该日 NAV；缺失即剔除，文末提示“总市值可能低估”。

- 抓取与报表职责分离：
  - 抓取（HTTP）：`fetch_navs` / `fetch_navs_range`（EastmoneyNavProvider）
  - 报表/确认（只读本地）：LocalNavProvider 读取 `navs` 表

- 区间抓取：
  - `python -m src.jobs.fetch_navs_range --from YYYY-MM-DD --to YYYY-MM-DD`
  - 闭区间逐日抓取（严格只抓指定日），幂等 upsert；失败清单在任务末尾汇总打印

- 推荐每日顺序：
  - `fetch_navs --date T` → `confirm_trades --day T+1` → `daily_report --as-of T`

- 代码落点：
  - 展示日参数：`src/usecases/portfolio/daily_report.py`（build/send 接受 as_of）
  - CLI/Job 参数：`src/app/main.py`（status），`src/jobs/daily_report.py`，`src/jobs/fetch_navs_range.py`
  - 确认口径：`src/core/trading/settlement.py` 与 `src/usecases/trading/confirm_pending.py`

如果你要新增功能，请先确认是否影响上述口径或职责边界；若需要改动，请在 PR 里同步更新 `docs/operations-log.md` 与 `docs/roadmap.md`。


---

## 5. 当前阶段范围与禁止事项

当前阶段（以 `docs/roadmap.md` 为准，主要是 v0.2「可信 & 可用的支付宝闭环」和 v0.3「为 AI 打基础」）**明确不做**：

1. **历史导入模块（v0.3 以后才真正实现）**
   - 在处理 v0.2 任务时，不实现 CSV/表格历史交易导入功能。
   - 如需预留入口，只能写 TODO 注释或简单占位，具体逻辑留到明确做 v0.3 相关任务时再实现。

2. **盘中估值（v0.3 以后才作为附加信息）**
   - 在处理 v0.2 任务时，不接入实时估值，所有核心计算基于**每日官方净值**。
   - 盘中估值只在 roadmap 指到的版本中按“附加字段 + 明确标注”方式实现。

3. **AI 产品功能**
   - 不在业务代码中接入任何 LLM / AI 推理，不实现“AI 帮你决策/聊天问答”这类产品功能。
   - 允许按照 `docs/roadmap.md` 中的规划，增加与 AI 相关的数据准备结构（例如 `action_type` / `who_decided` / `tags` / `ContextSnapshot` / `Outcome` 等），但这些只是数据层，不直接调用模型。

4. **复杂错误处理与审计**
   - 不做统一错误模型、重试机制、审计日志等
   - 不引入额外的安全/合规模块

5. **破坏性操作与大规模重构**
   - 禁止：
     - 删除或重命名顶层目录（src/docs/jobs/data/scripts）
     - 清空或重建 SQLite 数据库结构
     - 大范围格式化或重写无关代码
   - 若确有必要，必须先给详细计划，并经我确认

---

## 6. 你应该如何提问

当你不确定时，请优先用中文向我确认，例如：

- "当前任务是否允许修改 schema？"
- "这个 TODO 是现在实现，还是留到未来版本？"
- "是否可以新增第三方依赖 X？用途是 Y。"

**不要**在不确定的情况下自行做出破坏性改动或新依赖选择。

---

## 7. 工具使用策略（MCP）

### Code-Index MCP 使用指导

**何时使用 Code-Index MCP：**
- **大范围代码搜索**：搜索整个项目或多个目录时
- **复杂模式匹配**：需要正则表达式或高级搜索功能
- **项目结构分析**：理解代码库整体架构和依赖关系
- **性能敏感场景**：大型项目中的快速搜索和索引

**何时使用普通搜索工具（Grep/Glob）：**
- **局部代码查看**：只看几个特定文件或目录
- **简单字符串搜索**：直接的字面量匹配
- **快速定位**：已知文件位置的精确查找
- **小范围修改**：1-3个文件的简单修改任务

**指令触发方式：**
- **主动指令**："用 code-index 搜索所有包含 Trade 的文件"
- **建议使用**：在分析复杂代码结构时我会询问是否使用高级搜索
- **自动选择**：对于跨多个目录的搜索任务，我会优先考虑使用 MCP

**注意**：MCP 工具需要手动配置和初始化，如果索引未建立会先进行项目索引。

### Sequential-Thinking MCP 使用指导

**何时使用 Sequential-Thinking：**
- **复杂架构分析**：需要逐步推理的设计任务
- **多步骤问题解决**：需要分解为多个逻辑步骤的复杂问题
- **技术方案推演**：需要深入分析各种可能的解决方案
- **系统性代码审查**：需要全面分析代码质量和架构

**指令触发方式：**
- **主动指令**："用 sequential-thinking 分析这个架构设计问题"
- **建议使用**：遇到复杂任务时我会询问是否使用结构化思考

### Exa MCP 使用指导

**何时使用 Exa：**
- **技术调研**：查找最新的技术文档、最佳实践和API说明
- **代码示例搜索**：获取特定库、框架或编程模式的使用示例
- **问题解决**：搜索实际开发中遇到的具体技术问题
- **学习新技术**：快速获取新技术的核心概念和实现代码

**两种搜索模式：**
- **Web搜索**：获取最新的网络内容和文档
- **代码上下文搜索**：专门针对编程任务优化的代码示例

**指令触发方式：**
- **主动指令**："用 exa 搜索 Python Decimal 最佳实践"
- **建议使用**：需要最新技术信息或代码示例时我会询问是否使用专业搜索

---

### Explore Subagent 与 MCP 协作规范

**Explore subagent 职责：**
- 只用于**探索和理解代码库**，产出结构化上下文（模块划分、调用链等）
- **不直接进行具体实现级改动**
- 典型任务："错误处理在哪一层？" "模块划分是怎样的？"
- 不适合：精确定位某个函数、修改具体文件（用 Grep/Edit）

**Explore 与 Code-Index MCP 关系：**
- 策略层 vs 搜索引擎层，两者**可组合而非强耦合**
- Explore 优先使用 Grep/Glob 进行局部搜索
- 跨项目/多目录/复杂模式时，才在明确提出后调用 Code-Index MCP

**工具调用优先级：**
1. 简单查询/修改 → Grep/Glob/Read/Edit
2. 代码探索 → Explore subagent（内部按需用基础工具）
3. 大规模搜索 → Explore + Code-Index MCP
4. 复杂推演 → Sequential-Thinking MCP
5. 外部调研 → Exa MCP

感谢配合！
