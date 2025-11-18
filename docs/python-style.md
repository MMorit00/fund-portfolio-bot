# Python 代码规范（MVP）

目标：简洁、可读、稳定，便于后续扩展。

- 类型注解：全部启用（函数参数/返回值/主要字段）。
- Docstring：中文，说明职责/输入/输出/注意事项。
- 金额/净值/份额：使用 `decimal.Decimal`，禁止 float 参与金融计算。
- 舍入与保留：金额 2 位、净值 4 位、份额 4 位（可配置，保持一致）。
- 文件命名：snake_case；路径表达语义，文件名尽量简短。
- 导入顺序：`__future__` → 标准库 → 第三方 → 项目内部（由 ruff 自动维护）。
- 目录职责：
  - `core` 仅含纯领域逻辑，不依赖外部库实现
  - `usecases` 仅依赖 `core` 与 `ports`（Protocol）
  - `adapters` 实现具体技术，供 `app/wiring` 装配
  - `jobs` 仅做参数解析与调用 usecase，不写业务
- 错误处理：核心抛异常；入口捕获并 `print`。
- 日志：使用 `app/log.py` 的 `log()`；不引 logging 框架。
- SQL 打印：通过 SQLite trace 回调；可用 `ENABLE_SQL_DEBUG` 控制。

## 类型与注解规范

- 新代码统一使用内置泛型与现代语法：`list[...]` / `dict[...]` / `X | None` 等；
  老代码遇到实质改动时再顺手从 `List`/`Dict` 等迁移，无需一次性全局替换。
- 核心层（`src/core`、`src/usecases`）禁止使用 `Any`；适配层仅允许在外部边界
 （HTTP/DB/未建模 JSON）短暂出现 `Any`，进入领域前尽快收敛为明确类型。
- 公共函数/方法必须显式标注返回类型，避免隐式推断为 `Any`。
- 容器类型尽量具体化，避免长期保留 `dict[str, Any]` 这类“黑箱容器”；固定结构优先
  使用 `@dataclass(slots=True)` 或 `TypedDict` 作为 DTO。
- 必要时使用 `cast` 或 `# type: ignore`，需要在同一行给出简短中文说明“为何安全/为何必要”，
  禁止作为掩盖类型问题的万能胶水。

- 只读容器约束：
  - 入参优先使用 `Mapping[...]`/`Sequence[...]` 表达只读语义；返回值再用 `dict/list`。

- 封闭取值域：
  - 关闭集合使用 `Literal[...]` 或枚举（如 `AssetClass`/`TradeStatus`）；需要复用时用 `TypeAlias` 命名类型别名，避免“自由字符串”。

- Optional 传播最小化：
  - 语义需要“有/无”时返回 `X | None`，并在边界尽早判空；
  - 能返回空容器时优先返回空容器而非 `None`。

- Any 审计与 mypy 开关（建议）：
  - 在类型检查配置中启用：`disallow-any-generics`、`disallow-incomplete-defs`、`warn-unused-ignores`、`no-implicit-optional`，降低 `Any` 渗透。

- DTO/数据类约定：
  - 领域/DTO 类优先 `@dataclass(slots=True)`；明确不可变时可用 `frozen=True`；避免“黑箱 dict”作为长期结构。

- 常量与命名：
  - 需要稳定不可变的配置用 `Final[...]`；避免一字母变量名，提升可读性与可检索性。
  - **状态标记值使用小写**：对于数据库字段或 API 中的状态标记（如 `confirmation_status`、`delayed_reason`），统一使用**小写**字符串值（如 `"normal"` / `"delayed"` / `"nav_missing"`），便于阅读和调试。避免使用全大写（`"NORMAL"`）或驼峰（`"NavMissing"`）。

- 端口与分层：
  - 对外依赖统一走 `Protocol`（结构化类型），UseCase 仅依赖端口与领域模型，不引用具体适配器类型。

### 示例（好 vs 不好）

```python
# ✅ 好：明确的数据结构与类型
from dataclasses import dataclass
from typing import Mapping

@dataclass(slots=True)
class Position:
    fund_code: str
    shares: Decimal

def total_shares(positions: Mapping[str, Position]) -> Decimal:
    return sum(p.shares for p in positions.values())

# ❌ 不好：黑箱 dict 与 Any
def total_shares_bad(positions: dict[str, object]) -> Decimal:  # type: ignore[示例：黑箱容器]
    return sum(p["shares"] for p in positions.values())  # 结构不透明
```

```python
# ✅ 好：封闭取值域与 Literal
from typing import Literal
Action = Literal["buy", "sell", "hold"]

# ❌ 不好：自由字符串
Action = str  # 难以检查与约束
```


## Docstring 与注释风格

- 统一使用三引号中文 docstring，优先说明“做什么”和关键业务规则。
- 充分信任类型注解，docstring 中不重复写类型，仅在有特别含义时补充说明。
- 类/UseCase/Protocol 必须写 docstring；公开方法和复杂内部方法建议写，简单工具函数可视情况省略或写一行注释。
- 模块级 docstring 用于说明模块职责与注意事项（尤其是涉及业务口径的模块，如交易确认、再平衡等）。
- 对外暴露的函数/方法、或参数含义复杂时，建议使用 `Args:` / `Returns:` 块说明业务语义、取值约束和副作用。（公共 API / Protocol 的实现，对外暴露给别的模块或脚本频繁调用）
- 避免机械、过度冗长的 Args/Returns 描述：不重复写类型信息，仅保留对理解业务有帮助的说明（类型信息以注解为准）。

## Import 顺序规范（ruff isort）

项目使用 ruff 自动维护 import 顺序，无需手动调整。

### 分组规则（组间用空行分隔）

```python
# 1. __future__ imports（特殊，单独一组）
from __future__ import annotations

# 2. 标准库（Python 内置模块）
import os
import sqlite3
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal, Protocol

# 3. 第三方库（如 httpx、fastapi 等）
import httpx

# 4. 本项目模块（src.*）
from src.adapters.db.sqlite.fund_repo import SqliteFundRepo
from src.core.asset_class import AssetClass
from src.usecases.ports import AllocConfigRepo, FundRepo
```

### 组内排序规则

1. **`import` 语句优先于 `from...import`**
2. **同类型 import 按模块名字母序排序**
3. **同一模块的多个导入合并到一行，并按字母序排列**

```python
# ✅ 正确
from src.usecases.ports import AllocConfigRepo, FundRepo, NavProvider

# ❌ 错误（会被 ruff 自动合并与排序）
from src.usecases.ports import FundRepo
from src.usecases.ports import AllocConfigRepo
```

### 工具配置

在 `pyproject.toml` 中已配置：

```toml
[tool.ruff.lint]
select = ["F", "E", "I"]  # I = isort（import 排序）

[tool.ruff.lint.isort]
known-first-party = ["src"]  # 标记 src.* 为本项目模块
```

### 日常使用

```bash
# 自动修复 import 顺序
ruff check --select I --fix .

# 或者修复所有可修复问题
ruff check --fix .
```

**原则**：交给工具自动维护，不手动调整顺序。
