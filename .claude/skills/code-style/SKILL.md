---
name: code-style
description: Applies the fund-portfolio-bot Python coding conventions, including type hints, Decimal usage, docstrings, and module organization. Use when writing, editing, or reviewing Python code in this repository.
---

# Python code style for fund-portfolio-bot

本 Skill 强调编码规范中最关键、最容易被忽略的规则。

> 完整编码规范见 `CLAUDE.md` 第 3 节（核心约束）。
> 分层架构约束见 `.claude/skills/architecture/SKILL.md`。

## When to use

在以下场景使用本 Skill：

- 生成新的 Python 模块（尤其是 `src/` 下）
- 修改现有函数或类
- 做代码重构或代码评审

## 类型与数值正确性

- 所有函数参数与返回值都应添加类型注解。
- 优先使用现代类型语法：
  - `list[str]`, `dict[str, Decimal]`, `X | None`
  - 避免使用 `List` / `Optional` 等老式写法，除非项目已有统一约定。
- 金额、净值、份额等金融相关字段一律使用 `Decimal`。
- 不要使用 `float` 做任何金融计算。

## Docstring 与注释

- 公开的类与函数应该有简洁的中文 docstring，说明：
  - 主要职责
  - 关键业务约束或注意点
- Docstring 不需要重复类型信息（类型以注解为准）。
- **数字标签注释**（CLI 层规范）：
  - 函数内部用 `# 1.` `# 2.` `# 3.` 标记逻辑步骤
  - 示例：`# 1. 解析参数` → `# 2. 调用 Flow` → `# 3. 格式化输出`
- 注释只在业务规则不直观时补充解释，避免噪音注释。

## 模块与类内部结构

原则：**入口在上，工具在下；公开在上，私有在下。**

类内部顺序：

1. `__init__`
2. 公共方法
3. 以 `_` 开头的私有辅助方法

模块内部顺序：

1. import（按标准库 / 第三方 / 本地分组）
2. 公共类与公共函数
3. 仅模块内部使用的私有工具函数（例如 `_helper_*`）

## 命名惯例

- 状态类字段或枚举值用小写字符串，例如：
  - `"normal"`, `"delayed"`, `"pending"`
- 文件名、函数名、变量名：`snake_case`
- 类名：`PascalCase`
- **CLI 层函数命名**（v0.4.2+ 统一规范）：
  - `_parse_args()`：参数解析函数
  - `_format_*()`：格式化输出辅助函数（如 `_format_result()`, `_format_fees()`）
  - `_do_*()`：命令执行函数（如 `_do_buy()`, `_do_list()`, `_do_confirm()`）
  - `main()`：CLI 主入口，只做路由

## 分层与配置相关约束

- `core` 层代码不要从 `adapters` 或 `app` 导入。
- 业务逻辑中避免直接使用 `os.getenv`：
  - 优先通过已有的配置模块或适配层获取配置。

## DCA & AI 分工命名规范

本项目是 **AI 驱动** 的投资工具。在 DCA、历史扫描、AI 分析相关代码中，严格遵循 **"规则算事实，AI 做解释"** 的分工原则，通过命名来强化这个边界。

### 规则层数据模型

规则层只输出可重算的结构化事实，严禁直接生成主观结论。

| 后缀 | 定义 | 示例 |
|------|------|------|
| `*Facts` | 对象在特定时期的客观数据聚合（日期、金额、间隔等）；作为 Context 供 AI 使用 | `FundDcaFacts` |
| `*Check` | 单条数据针对规则的验证结果（命中+偏差+说明），不下结论 | `DcaTradeCheck` |
| `*Flag` | 规则识别的"值得注意"的点（异常、中断等），仅标记不定性 | `TradeFlag` |
| `*Draft` | 建议方案（永远不对应 DB 表，只是内存结构） | `DcaPlanCandidate` |
| `*Result` | 内部中间聚合结果 | `BackfillResult` |
| `*Report` | CLI/AI 展示用的汇总报告 | `ScanReport` |

### Flow 函数动词

| 动词 | 约束 | 示例 |
|------|------|------|
| `build_*_facts()` | 只读，纯计算/聚合，返回 `*Facts` | `build_dca_facts_for_batch()` |
| `scan_*()` | 只读，无副作用（Idempotent），可随意调用 | `scan_trading_history()` |
| `draft_*()` | 返回 `*Draft` 对象，不入库 | `draft_dca_plan()` |
| `backfill_*()` | **写操作**，修改 Truth Layer，需谨慎 | `backfill_dca_for_batch()` |

**关键原则**：看到 `scan_` 就知道安全可调；看到 `backfill_` 就要警惕会修改数据。

### AI 层（预留）

AI 基于规则层的 `*Facts` 生成语义解释，仅写入解释性字段，不修改核心数据。

- `*Insight`：洞察（如"这笔交易可能是限额"）
- `*Explanation`：自然语言解释
- `*Label`：分类标签

## 提交前检查

在可能的情况下：

- 运行静态检查（例如项目中配置的 `ruff check --fix .`）。
- 快速浏览本次 diff，确认：
  - 风格清理没有改变业务行为
  - 没有遗留调试代码（例如 `print`、`breakpoint()`）。
