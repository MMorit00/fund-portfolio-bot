# 开发决策记录

> 本文档记录关键架构与业务决策。
> 完整规则见 `docs/settlement-rules.md` / `docs/architecture.md`。

---

## 2025-11-26 v0.4 行为数据（action_log）

### 背景

为后续 AI 分析准备数据基础。核心问题：如何记录用户的投资行为，让 AI 能理解"你做了什么"和"为什么这样做"。

### 设计决策

**1. 只建一张表**：
- 只做 `action_log`，不做 `ContextSnapshot` / `Outcome`
- 理由：快照和结果可从 `trades` / `navs` 动态计算，无需预存
- 真正需要固化时再加表（验证驱动）

**2. 字段精简（7 个）**：
```
id, action, actor, acted_at, trade_id, intent, note
```
- 去掉 `source`：`action` + `actor` 组合已足够区分来源
- 去掉 `plan_id`：可通过 `trade_id` 追溯
- 去掉 `fund_code`：可通过 `trade_id` JOIN `trades` 查到
- 去掉 `extra`：有 `note` 就够，JSON 扩展是过度设计

**3. `intent` 固定枚举**：
```python
Intent = Literal["planned", "impulse", "opportunistic", "exit"]
```
- 固定选项保证数据一致性，方便统计
- 特殊情况写 `note`

**4. 埋点原则**：
- 只记录用户的**决策行为**，不记录系统自动处理
- 确认结果从 `trades` 表查询（status/confirm_date）
- DCA 自动执行通过 `_log_action=False` 禁用埋点

| Flow 函数 | action | actor | 备注 |
|-----------|--------|-------|------|
| `create_trade` | `buy` / `sell` | `human` | 仅 `_log_action=True` 时记录 |
| `run_daily_dca` | - | - | 调用 `create_trade(_log_action=False)` |

### Schema 变更

- `SCHEMA_VERSION`：4 → 5
- 新增 `action_log` 表

### 修改文件

**新增**：
- `src/core/models/action.py`：`ActionLog` 数据类
- `src/data/db/action_repo.py`：`ActionRepo` 仓储

**修改**：
- `src/data/db/db_helper.py`：DDL
- `src/core/container.py`：注册 `action_repo`
- `src/flows/trade.py`：埋点 + 新增 `intent` / `note` 参数
- `src/cli/trade.py`：`--intent` / `--note` 参数

**文档**：
- `docs/sql-schema.md`：action_log 表说明

### 不做的事

- ❌ 不建 ContextSnapshot / Outcome 表
- ❌ 不做 DCA 行为埋点（留到后续版本）
- ❌ 不做历史数据回填

---

## 2025-11-26 v0.4.1 行为数据增强（埋点扩展）

### 背景

v0.4 完成基础埋点后，扩展更多用户行为记录，完善行为数据查询能力。

### 完成内容

**1. Intent 扩展**：
- 新增 `"rebalance"` 意图标签，支持用户标注"再平衡"操作
```python
Intent = Literal["planned", "impulse", "opportunistic", "exit", "rebalance"]
```
- 用法：`trade buy --fund 000001 --amount 5000 --intent rebalance --note "按建议补仓"`

**2. cancel_trade 埋点**：
- 新增 `"cancel"` 行为记录，记录用户取消交易决策
```python
ActionType = Literal["buy", "sell", "dca_skip", "cancel"]
```
- 埋点设计：`action="cancel"`, `actor="human"`, `trade_id` 关联被取消的交易
- CLI 支持：`trade cancel --id 123 --note "市场过热"`

**3. action list CLI**：
- 新增 `src/cli/action.py`：行为日志查询工具
- 功能：`action list --days 30`（查询最近 N 天行为）
- 格式化输出：图标 + 时间 + trade_id + intent + note

| 埋点覆盖 | action | actor | 触发场景 |
|----------|--------|-------|----------|
| 手动买入/卖出 | `buy` / `sell` | `human` | `create_trade(_log_action=True)` |
| 跳过定投 | `dca_skip` | `human` | `skip_dca` |
| 取消交易 | `cancel` | `human` | `cancel_trade` |

### 修改文件

**修改**：
- `src/core/models/action.py`：扩展 `ActionType` 和 `Intent` 枚举
- `src/flows/trade.py`：`cancel_trade` 添加 `note` 参数和埋点逻辑
- `src/cli/trade.py`：buy/sell 支持 `--intent rebalance`，cancel 支持 `--note`

**新增**：
- `src/cli/action.py`：行为日志查询 CLI（~100 行）

### 设计原则

**埋点一致性**：
- 所有 `actor="human"` 的行为都记录
- 保持 action + actor 组合的语义清晰
- note 字段用于记录用户决策原因

**CLI 设计**：
- `action list`：只查询，不修改
- 图标化输出：📈 买入、📉 卖出、⏭️ 跳过定投、❌ 取消
- 时间格式：YYYY-MM-DD HH:MM（易读）

### 验证结果

- ✅ `--intent rebalance` 可用于标注再平衡操作
- ✅ `cancel_trade` 自动记录到 action_log
- ✅ `action list` 正确显示最近行为记录
- ✅ 所有修改符合项目编码规范

---

## 2025-11-26 v0.3.4+ 闭环完善（月度定投 + 手动确认 + 日历管理）

### 完成内容

**问题定位**：
- v0.3.3 完成再平衡独立 CLI 后，业务闭环分析发现 2 个 P1 断点：
  1. 月度定投 rule=31 在短月永不触发（2 月/4 月等）
  2. NAV 永久缺失无手动确认路径（只能用 SQL 绕过）
- P0 任务：文档需补充 calendar sync/patch 用法

**解决方案**：
- 修复月度定投短月顺延逻辑（~30 行）
- 新增 `trade confirm-manual` CLI（~100 行）
- 更新文档：calendar 管理完整用法 + 依赖说明
- 优化错误消息：提供降级路径提示

**新增功能**：
- `trade confirm-manual --id <ID> --shares <份额> --nav <净值>`：手动确认延迟交易
  - 使用场景：支付宝订单已成功，但系统 NAV 持续缺失（基金停牌/数据源故障）
  - 安全控制：只能确认 pending 状态交易，NAV 和 shares 必须 > 0

**修改文件**：
- `src/flows/dca.py`：_is_plan_due() 修复短月逻辑
- `src/flows/trade.py`：新增 confirm_trade_manual() 函数
- `src/cli/trade.py`：新增 confirm-manual 子命令
- `src/flows/calendar.py`：优化错误消息（提供降级路径）
- `src/core/container.py`：修复 DbHelper 导入
- `docs/operations-log.md`：补充 calendar sync/patch 用法 + 依赖说明
- `docs/settlement-rules.md`：更新日历管理说明 + 手动确认流程
- `docs/sql-schema.md`：更新路径引用 + Schema v4 说明

### 技术决策

**1. 月度定投短月顺延**：
```python
# 修复前
return int(plan.rule) == day.day  # ❌ rule=31 在 2 月永不触发

# 修复后
target_day = int(plan.rule)
_, last_day = monthrange(day.year, day.month)
effective_day = min(target_day, last_day)  # ✅ 短月顺延到月末
return day.day == effective_day
```

**2. 手动确认设计原则**：
- **显式操作**：明确的 `confirm-manual` 子命令，不与自动确认混淆
- **参数验证**：NAV 和 shares 必须 > 0，防止误操作
- **状态检查**：只能确认 pending 状态交易，确认后无法撤销
- **延迟重置**：自动重置 confirmation_status/delayed_reason/delayed_since

**3. 错误消息优化策略**：
- **多方案提示**：不只提示安装依赖，还提供降级路径（CSV 导入）
- **层次清晰**：优先方案（uv sync）→ 备选方案（单独安装）→ 降级路径（其他命令）
- **用户友好**：多行格式，使用缩进和序号

**4. 文档更新原则**：
- **当前版本优先**：重点说明 v0.3.4+ 的用法
- **删除过时内容**：移除已废弃的 scripts/import_trading_calendar.py 说明
- **路径一致性**：统一使用 v0.3.1 后的路径（data/db/ 而非 adapters/db/sqlite/）

### 代码质量

- ✅ Ruff 检查全部通过（修复 1 处缺失导入）
- ✅ 完全符合项目编码规范
- ✅ 代码量：~200 行（符合"小步修改"原则）

### 影响范围

- 修改文件：6 个 Python 文件 + 3 个文档
- 新增功能：1 个 CLI 子命令（confirm-manual）
- 修复断点：2 个 P1 断点（月度定投 + 手动确认）
- 文档更新：补充 calendar 用法 + 优化路径引用

### 验证结果

- ✅ 业务闭环：100% 完整（配置/日常/异常/日历/边界场景全部覆盖）
- ✅ 月度定投：rule=31 在 2 月 28 日正确触发
- ✅ 手动确认：延迟交易可通过 CLI 手动确认
- ✅ 文档完整：calendar 用法清晰 + 依赖说明完善

---

## 2025-11-23 v0.3.3 再平衡独立 CLI + 基金级别建议

### 完成内容

**问题定位**：
- v0.3.2 完成配置管理闭环后，发现再平衡功能有两个痛点：
  1. 缺少独立 CLI：用户必须跑完整日报才能查看再平衡建议（不够灵活）
  2. 建议粒度粗糙：只给出资产类别级别建议（"国内权益买 5000"），不知道买哪只基金

**解决方案**：
- 新增独立 CLI 入口（~107 行）
- 增强基金级别建议（~110 行）

**新增文件**：
- `src/cli/rebalance.py`：独立再平衡 CLI（支持 `--as-of` 参数）

**修改文件**：
- `src/flows/report.py`：
  - 新增 `FundSuggestion` 数据类
  - 增强 `RebalanceResult`：添加 `fund_suggestions` 字段
  - 新增 `_suggest_specific_funds()` 函数：智能分配金额到具体基金

### 技术决策

**基金分配策略**：
- **买入策略**：平均化持仓（优先推荐持仓较小的基金）
- **卖出策略**：渐进式减仓（优先推荐持仓较大的基金）
- **智能降级**：无持仓的资产类别只显示资产类别级别建议

---

## 2025-11-22 v0.3.2 配置管理 CLI（闭环完成）

### 完成内容

**问题定位**：
- v0.3.1 完成架构重构后，发现用户必须直接操作数据库才能配置基金、定投计划、资产配置
- 破坏了"命令行工具"的定位，无法形成完整业务闭环

**解决方案**：
- 新建 4 个配置管理 CLI 模块（~400 行）
- 补全仓储层的 upsert/list 方法（~100 行）
- 新建 Flow 层配置管理函数（~200 行）

**新增文件**：
- `src/flows/config.py`：8 个配置管理 Flow 函数
- `src/cli/fund.py` / `dca_plan.py` / `alloc.py` / `trade.py`：配置管理 CLI
- `src/core/models/alloc_config.py`：AllocConfig 数据类

**Schema 变更**（v3 → v4）：
- `dca_plans` 表增加 `status TEXT NOT NULL DEFAULT 'active'` 字段

### 技术决策

**CLI 设计原则**：
- 子命令模式：每个 CLI 文件支持多个子命令（add/list/set/show 等）
- 职责单一：只负责参数解析和结果展示，业务逻辑在 Flow 层

**定投计划状态管理**：
- 新增 `status` 字段（active/disabled）：支持临时禁用而不删除配置
- 新增 `enable_dca_plan()` 函数：对称设计（disable/enable 成对）

---

## 2025-11-22 v0.3.1 架构简化与依赖注入

### 完成内容

**目录结构重组**：
- `jobs/` → `cli/`：命令行入口
- `usecases/` → `flows/`：业务流程（8 个类合并到 4 个文件）
- `adapters/` → `data/`：数据访问层
- `core/` 重组为 `models/` + `rules/`

**删除抽象层**：
- 删除 `protocols.py`（210 行 Protocol 定义）
- 删除 `wiring.py`（150 行 DependencyContainer）
- 所有 Repo/Service 类去除 Protocol 继承

**类名简化**：
- `SqliteTradeRepo` → `TradeRepo`
- `DbCalendarService` → `CalendarService`
- 等 7 个类名简化

**依赖注入重构**：
- 新建 `src/core/dependency.py`：`@dependency` 装饰器
- 新建 `src/core/container.py`：集中管理 9 个依赖工厂函数
- Flow 层改为纯函数 + 自动依赖注入

### 技术决策

**删除 Protocol 和 DI 的理由**：
- 单 DB 实现（只有 SQLite），不需要多实现抽象
- Protocol 主要服务于依赖注入和测试 mock，当前不做单元测试
- 减少类型系统复杂度

**依赖注入设计原则**：
- 显式注册：所有可注入依赖必须通过 `@register` 显式注册
- 命名一致：注册名必须与函数参数名完全一致
- 可覆盖：调用时传入的非 None 参数不会被覆盖

---

## 历史版本要点

### v0.3 日历与接口重构
- 统一日历协议：`CalendarService`（严格 DB 模式）
- SettlementPolicy 引入：三层日历组合（guard + pricing + lag_counting）
- pricing_date 持久化（Schema v3）

### v0.2.1 交易确认延迟追踪
- 延迟标记机制：confirmation_status / delayed_reason / delayed_since
- 日报展示延迟交易：显示延迟天数和建议
- 自动恢复：补充 NAV 后自动确认

### v0.2 严格 NAV 口径
- 展示日逻辑：默认上一交易日
- NAV 严格不回退：缺失则跳过并提示
- 区间抓取：`fetch_navs_range` 命令

> **历史决策归档**：更早期的决策（v0.1 MVP 等）已归档。
