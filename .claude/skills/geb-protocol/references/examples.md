# GEB 协议示例

## Python 项目示例（fund-portfolio-bot）

### Root: CLAUDE.md

```markdown
# Portfolio Engine

个人基金投资管理工具。聚合公募基金持仓、管理定投与 T+1/T+2 确认、计算资产配置与权重、生成文本日报并推送。

模块路由：
src/
├── cli/      命令行入口       → 见 _dir.md
├── flows/    业务流程         → 见 _dir.md
├── core/     核心逻辑         → 见 _dir.md
└── data/     数据访问层       → 见 _dir.md

分层：cli → flows → core → data
```

### Folder: src/core/_dir.md

```markdown
核心逻辑层（领域模型 + 业务规则 + 依赖注入）
Input: 无外部依赖（最内层）
Output: models/, rules/, config, container, dependency
Pos: 最内层，被 flows/data/cli 依赖

子模块: models(数据类) + rules(纯规则) + container(DI容器)
```

### Folder: src/flows/_dir.md

```markdown
业务流程层（用例编排）
Input: core.models, core.rules, @dependency 注入的 Repo/Service
Output: create_trade(), confirm_trades(), make_daily_report() 等 Flow 函数
Pos: 中间层，被 cli 调用，依赖 core，通过 DI 获取 data 层实现

流程函数均为纯函数 + @dependency 装饰器
```

### Folder: src/data/_dir.md

```markdown
数据访问层（外部交互）
Input: core.models, 外部系统（DB/HTTP/Discord）
Output: TradeRepo, FundRepo, NavRepo, EastmoneyNavService, DiscordClient
Pos: 最外层，实现 core 定义的协议，被 DI 容器注册

子模块: db/(数据库 Repo) + client/(外部客户端)
```

### Folder: src/cli/_dir.md

```markdown
命令行入口（参数解析 + Flow 调用）
Input: flows 函数, argparse/click
Output: CLI 命令（fund, trade, report, dca 等）
Pos: 应用边界，只做参数解析，不写业务逻辑

每个模块对应一个子命令
```

### File: src/core/models/trade.py

```python
# Input: Decimal, datetime, Enum
# Output: Trade, TradeType, TradeStatus
# Pos: core/models 领域模型

from dataclasses import dataclass
from decimal import Decimal
from datetime import date
from enum import Enum

class TradeType(Enum):
    """交易类型"""
    BUY = "buy"
    SELL = "sell"

@dataclass
class Trade:
    """交易记录"""
    fund_code: str
    trade_type: TradeType
    amount: Decimal
    # ...
```

### File: src/core/rules/settlement.py

```python
# Input: Trade, date, CalendarProtocol
# Output: calc_confirm_date(), is_trade_confirmed()
# Pos: core/rules 纯业务规则

from datetime import date, timedelta
from ..models.trade import Trade

def calc_confirm_date(trade: Trade, calendar: CalendarProtocol) -> date:
    """计算确认日期（T+1/T+2）"""
    # ...
```

### File: src/flows/trade_flow.py

```python
# Input: Trade, @dependency(TradeRepo, FundRepo)
# Output: create_trade(), list_trades(), confirm_trades()
# Pos: flows 层，业务流程编排

from src.core.dependency import dependency
from src.core.models.trade import Trade

@dependency
def create_trade(
    trade_repo: TradeRepo,
    fund_repo: FundRepo,
    trade: Trade,
) -> TradeResult:
    """创建交易记录"""
    # ...
```

### File: src/data/db/trade_repo.py

```python
# Input: sqlite3, Trade, DbSession
# Output: TradeRepo (实现 TradeRepoProtocol)
# Pos: data/db 数据库访问

from src.core.models.trade import Trade

class TradeRepo:
    """交易记录数据库访问"""

    def save(self, trade: Trade) -> int:
        """保存交易记录"""
        # ...
```

---

## 原理

来源：赵纯想的"GEB 协议"（哥德尔、埃舍尔、巴赫 - 分形自指结构）

核心思想：
- **显性元数据 > 隐性记忆**：AI 无法真正记住复杂项目，但能读懂路标
- **分形结构**：每个层级都有完整的"我是谁"信息
- **自愈机制**：把"更新文档"作为代码任务的一部分，而非事后补充

---

## 与现有架构的对应

本项目已有的分层约束（见 `.claude/skills/architecture/SKILL.md`）：

```
cli → flows → core ← data
         ↓      ↑
         └──────┘（DI 注入）
```

GEB 协议补充的是**每个节点的自描述能力**，让 AI 无需回溯整个架构文档即可定位当前位置。
