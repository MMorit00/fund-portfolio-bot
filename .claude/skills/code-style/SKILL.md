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

## 分层与配置相关约束

- `core` 层代码不要从 `adapters` 或 `app` 导入。
- 业务逻辑中避免直接使用 `os.getenv`：
  - 优先通过已有的配置模块或适配层获取配置。

## 提交前检查

在可能的情况下：

- 运行静态检查（例如项目中配置的 `ruff check --fix .`）。
- 快速浏览本次 diff，确认：
  - 风格清理没有改变业务行为
  - 没有遗留调试代码（例如 `print`、`breakpoint()`）。
