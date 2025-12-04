# 开发决策记录

> 本文档记录关键架构与业务决策。
> 完整规则见 `docs/settlement-rules.md` / `docs/architecture.md`。

---

## 2025-12 行为语义增强

**ActionLog v2 设计**：引入 `strategy` 字段标记策略语境（`dca` / `rebalance` / `none`）
- 真相层：trades/navs/dca_plans 记录底层事实
- 故事层：action_log 记录行为时间线
- 简化实现：仅新增 strategy 字段，深度 DCA 字段留作 TODO

**Schema v13**：ActionLog 新增 `strategy TEXT` 字段，Flows 层埋点适配

---

## 2025-12 CLI 标准化重构

统一 `src/cli/` 代码结构：
- 职责分离：`_parse_args()` / `_format_*()` / `_do_*()` / `main()`
- 数字标签注释：函数内部用 `# 1.` `# 2.` 标记步骤
- 统一日志：全部使用 `log()`，标准返回码：0/4/5

---

## 2025-11 数据规范化

**移除 Trade.nav**：nav 已在 `navs` 表规范化存储，避免冗余
**命名规范**：Client vs Service 职责区分（I/O vs 业务逻辑）
**删除死代码**：清理未使用的迁移逻辑和函数

---

## 2025-11 历史账单导入

**支付宝账单解析**：GBK 编码，蚂蚁财富特征识别
**基金映射**：使用 `funds.alias` 字段匹配平台完整名称
**数据补全**：自动抓取 NAV，计算份额，补录 ActionLog

---

## 2025-11 行为数据（action_log）

**核心设计**：只记录用户决策行为，不记录系统自动处理
**字段精简**：`action, actor, source, acted_at, fund_code, target_date, trade_id, intent, note`
**Intent 枚举**：`planned, impulse, opportunistic, exit, rebalance`

---

## 2025-11 业务闭环完善

**月度定投修复**：rule=31 在短月顺延到月末
**手动确认**：`trade confirm-manual` 处理 NAV 永久缺失场景
**日历管理**：统一 DB 后端，支持 exchange_calendars + Akshare 修补

---

## 2025-11 架构简化

**目录重组**：`jobs→cli`, `usecases→flows`, `adapters→data`
**删除抽象层**：移除 Protocol 和复杂 DI，改为 `@dependency` 装饰器
**类名简化**：`SqliteTradeRepo→TradeRepo` 等

---

## 早期版本要点

**v0.3**：日历与接口重构，SettlementPolicy 三层日历组合
**v0.2**：严格 NAV 口径，交易确认延迟追踪
**v0.1**：MVP 功能实现（已归档）