# Portfolio Engine · Claude Code 协作说明

> 你是本项目的 Python 开发助手，只在**开发阶段**使用，不参与线上运行。人类始终是总指挥。

## 项目概述

本仓库是一个个人基金投资管理工具，目标是：

- 聚合公募基金持仓
- 管理定投与 T+1/T+2 确认
- 计算资产配置与权重
- 生成文本日报并通过 Discord Webhook 推送

> ⚠️ **重要**：当前阶段（MVP）**不做任何 AI 产品功能**，你只作为写代码/改代码的助手。

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
  python-style.md    # Python 编码规范
  operations-log.md  # 环境与运维记录
  coding-log.md      # 开发变更记录
  roadmap.md         # Roadmap 与大 TODO

data/
  portfolio.db       # SQLite 数据文件（实际创建后才存在）

scripts/
  backup_db.sh       # 手动 DB 备份脚本
```

在开始任何任务前，你应该优先阅读：

- `docs/architecture.md`
- `docs/python-style.md`
- `docs/roadmap.md`（了解当前版本目标）
- 最近几条 `docs/coding-log.md`（了解最新变更）


## 2. Python 编码规范（摘要）

> 详细规则以 `docs/python-style.md` 为准，这里只放你必须记住的关键点。

1. **类型注解必须写全**
   - 所有公开函数/方法都要写参数和返回值类型
   - 能用标准库类型就用标准库（`list[int]` / `dict[str, Any]`）

2. **数值使用 Decimal（涉及金额与净值）**
   - 禁止在业务层里用 float 做金额/净值计算
   - 在核心模型中统一用 `Decimal`，在边界（比如 SQLite / JSON）再做转换

3. **命名与文件布局**
   - 常量允许使用小写命名（项目内部约定），不用全大写
   - 文件名用小写+下划线，如 `trade.py`, `create_trade.py`
   - 目录负责表达语义：`core/trading/`, `usecases/portfolio/`，文件名尽量简短

4. **注释与 docstring**
   - **所有 docstring 一律使用中文**，说明"这个类/函数是干嘛的"和关键注意点
   - 行内注释只在必要时使用，用来解释"为什么这么做"，而不是"这行代码做什么"

5. **日志与 SQL 打印**
   - MVP 阶段不引入 logging 框架，只使用：
     - `app/log.py` 中的 `log()`（内部即 `print`）
     - SQLite 连接的 `set_trace_callback` 打印 SQL（可由配置开关控制）
   - 不要引入新的日志依赖库

6. **代码组织原则（重要）**
   - **入口在上，工具在下**：模块级别的入口函数/类放在文件最上方
   - **公开在上，私有在下**：
     - 类中：`__init__` → 公开方法 → 私有方法（`_method`）
     - 模块中：公开类/函数 → 模块私有函数（`_function`）
   - **示例（正确）**：
     ```python
     # ✅ 正确的组织方式
     class SqliteTradeRepo(TradeRepo):
         def __init__(self, conn): ...      # 构造函数
         def add(self, trade): ...           # 公开方法
         def list_pending(self): ...         # 公开方法
         def _internal_helper(self): ...     # 私有方法在后

     # 模块私有工具函数在类之后
     def _decimal_to_str(value): ...
     def _row_to_trade(row): ...
     ```
   - **反例（错误）**：
     ```python
     # ❌ 错误：工具函数在类之前
     def _decimal_to_str(value): ...  # 工具函数不应在前

     class SqliteTradeRepo(TradeRepo):
         def add(self, trade): ...
     ```

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

每次任务，你必须遵守以下步骤：

1. **先读项目，不要直接写代码**
   - 快速浏览相关目录和文档（architecture / python-style / roadmap / coding-log）
   - 用中文总结当前任务涉及的模块与边界（不超过 10 条）

2. **先给设计与计划**
   - 用列表说明：
     - 需要修改/新增哪些文件
     - 每个文件中要新增哪些类/函数
   - 标明：哪些是 MVP 内的功能，哪些只是 TODO 占位

3. **限制改动范围**
   - 默认情况下：一次任务**只修改 1~3 个文件**
   - 需要大范围重构时：
     - 先给我一份分步骤计划
     - 每一步都是一个"可单独完成的小任务"

4. **编码时的要求**
   - 遵守分层：
     - `core/` 不依赖 `usecases/` 或 `adapters/`
     - `usecases/` 只通过 `ports.py` 依赖外部
   - 业务逻辑写在 `core` / `usecases`，`adapters` 只做 IO/持久化
   - 为新增的公开类/函数写中文 docstring

5. **错误与日志策略（MVP）**
   - 不设计复杂错误体系，除入口脚本外一般不 try/except
   - 入口层（jobs 与 main）可以：
     - 捕获异常，输出 `log("任务失败：...")`，然后退出
   - 不要引入 logging/监控/审计相关第三方库

6. **文档同步**
   - 在做出"架构/行为上的决定"时，应该适当更新：
     - `docs/coding-log.md`（简要记录做了什么）
     - 必要时更新 `docs/architecture.md` 或 `docs/roadmap.md`


---

## 5. MVP 范围与禁止事项

当前阶段（v0.1）**明确不做**：

1. **历史导入模块**
   - 不实现 CSV/表格历史交易导入
   - 如需预留入口，只能写 TODO 注释，不实现逻辑

2. **盘中估值**
   - 不接入实时估值，所有计算基于**每日官方净值**

3. **AI 产品功能**
   - 不在业务代码中接入任何 LLM / AI 推理
   - 所有 AI 仅用于开发时的辅助（由人监督）

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

感谢配合！
