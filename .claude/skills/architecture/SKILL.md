---
name: architecture
description: Enforces the simplified layering and dependency rules for the fund-portfolio-bot project (v0.3.1), keeping cli, flows, core, and data correctly separated. Use when designing new components, changing imports, or reviewing architecture decisions.
---

# Architecture and layering for fund-portfolio-bot (v0.3.1)

本 Skill 关注分层职责与依赖方向。详细说明参见 `docs/architecture.md`。

## 层次结构概览（v0.3.1 简化版）

项目采用自外向内依赖的 3 层架构：

- `cli/`：命令行入口，参数解析 + 流程函数
- `flows/`：业务流程类，编排领域逻辑
- `core/`：纯核心逻辑
  - `models/`：领域数据类（Trade, Fund, DcaPlan 等）
  - `rules/`：纯业务规则函数（settlement, rebalance 等）
  - `config.py`, `log.py`：配置和日志
- `data/`：数据访问层
  - `db/`：数据库 Repo（TradeRepo, NavRepo 等）
  - `client/`：外部客户端（Eastmoney, Discord 等）

## 依赖规则（必须遵守）

依赖方向：**只能向内依赖**：

```
cli → flows → data
        ↓       ↓
      core ← ← ←
```

- `core/`
  - 只能依赖 `core/` 内部模块
  - **不得**导入 `cli/`、`flows/`、`data/`

- `flows/`
  - 可以依赖 `core/`（models + rules）
  - 可以依赖 `data/`（具体 Repo 和 Service 类）
  - **不得**导入 `cli/`

- `data/`
  - 可以依赖 `core/`（models + rules）
  - **不得**导入 `cli/`、`flows/`

- `cli/`
  - 可以依赖所有层（flows + data + core）
  - 只做参数解析和流程调用

## 关键约束

1. **无 Protocol 抽象层**：
   - v0.3.1 删除了 `protocols.py`
   - 直接使用具体类：`TradeRepo`、`NavRepo` 等
   - 类的方法签名即为"接口约定"

2. **无依赖注入容器**：
   - v0.3.1 删除了 `wiring.py`
   - CLI 中直接实例化 Repo 类
   - 使用 flow 函数封装业务逻辑

3. **避免循环导入**：
   - 如需 TYPE_CHECKING，使用 `from typing import TYPE_CHECKING`
   - 类型注解使用字符串形式：`"TradeRepo"`

## 设计或修改代码时的步骤

1. **识别所在层级**
   - 判断文件属于 `cli` / `flows` / `core` / `data` 中的哪一层
   - 确保其职责与该层定位一致：
     - 命令行入口 + 流程函数 → `cli`
     - 业务流程编排 → `flows`
     - 数据模型 + 纯规则 → `core`
     - 数据库访问 + 外部客户端 → `data`

2. **检查依赖方向**
   - 确保 import 语句符合依赖规则
   - `core` 不能 import `flows` 或 `data`
   - `flows` 不能 import `cli`

3. **命名约定**
   - Repo 类：`TradeRepo`、`NavRepo`（不带 Sqlite 前缀）
   - Service 类：`CalendarService`、`EastmoneyNavService`
   - Flow 类：动宾结构（`CreateTrade`、`ConfirmTrades`）
   - Flow 文件：`trade.py`、`dca.py`、`market.py`、`report.py`

4. **类型注解**
   - 使用具体类型：`TradeRepo`、`FundRepo`
   - 避免循环导入时使用 TYPE_CHECKING
   - 字符串类型注解：`def __init__(self, repo: "TradeRepo")`

## 违反规则示例（禁止）

```python
# ❌ core/ 中导入 data/
from src.data.db.trade_repo import TradeRepo  # 禁止

# ❌ flows/ 中导入 cli/
from src.cli.confirm import confirm_trades_flow  # 禁止

# ❌ data/ 中导入 flows/
from src.flows.trade import CreateTrade  # 禁止
```

## 正确示例

```python
# ✅ cli/ 调用 flows/ 和 data/
from src.flows.trade import ConfirmTrades
from src.data.db.trade_repo import TradeRepo
from src.data.db.calendar import CalendarService

def confirm_trades_flow(day: date):
    db = DbHelper()
    conn = db.get_connection()
    calendar = CalendarService(conn)
    trade_repo = TradeRepo(conn, calendar)
    usecase = ConfirmTrades(trade_repo, nav_service)
    return usecase.execute(today=day)

# ✅ flows/ 使用 TYPE_CHECKING
from typing import TYPE_CHECKING
from src.core.models.trade import Trade

if TYPE_CHECKING:
    from src.data.db.trade_repo import TradeRepo

class ConfirmTrades:
    def __init__(self, repo: "TradeRepo"):
        self.repo = repo
```

## 重构历史

- **v0.1-v0.3**：4 层架构（jobs → wiring → usecases(Protocol) → adapters）
- **v0.3.1**：3 层架构（cli → flows → data，删除 Protocol 和 wiring）
