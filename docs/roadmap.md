# Roadmap（版本规划）

## 产品定位

- **工具定位**：个人基金投资的"影子记账 + 决策辅助系统"
- **交易平台**：国内平台（优先支付宝）
- **同步模式**：伪同步——用户在平台完成操作后手动录入确认
- **报告口径**：基于官方日度净值，不做盘中交易
- **AI 定位**：当前仅做数据准备，不实现 AI 决策

## 版本总览

- ✅ **v0.1**：MVP 基础功能（交易录入、定投、NAV 抓取、确认、日报）
- ✅ **v0.2**：支付宝闭环（严格 NAV 策略、延迟追踪、再平衡）
- ✅ **v0.3**：日历策略化（SettlementPolicy、Schema v3）
- ✅ **v0.3.1**：架构简化（目录重构、删除抽象层）
- 🔜 **v0.4+**：增强功能（待规划）
- 🔮 **v1.x+**：AI 辅助决策（远期）

---

## v0.3.1（架构简化，✅ 已完成）

### 目标

在不新增功能的前提下简化代码结构，为未来扩展铺平道路。

### 完成内容

**✅ 目录结构重组**：
- `jobs/` → `cli/`：命令行入口
- `usecases/` → `flows/`：业务流程（8 个类合并到 4 个文件）
- `adapters/` → `data/`：数据层（db/ + client/）
- `app/` → `core/`：配置和日志移入核心层
- `core/` 重组为 `models/` + `rules/`

**✅ 删除抽象层**：
- 删除 `src/core/protocols.py`（Protocol 定义）
- 删除 `src/app/wiring.py`（DependencyContainer）
- 所有 Repo 类去除 Protocol 继承

**✅ 类名简化**：
- `SqliteTradeRepo` → `TradeRepo`
- `SqliteFundRepo` → `FundRepo`
- `SqliteNavRepo` → `NavRepo`
- `SqliteDcaPlanRepo` → `DcaPlanRepo`
- `SqliteAllocConfigRepo` → `AllocConfigRepo`
- `DbCalendarService` → `CalendarService`
- `SqliteDbHelper` → `DbHelper`

**✅ Flow 函数模式**：
- CLI 文件中采用 `xxx_flow()` 函数封装业务逻辑
- 直接实例化具体 Repo 类，无依赖注入

**✅ 验证通过**：
- Ruff 检查：全部通过
- 功能测试：CLI 命令正常运行
- Schema 版本：保持 v3 不变

### 架构对比

**Before（4 层）**：
```
Jobs → DependencyContainer → UseCase (Protocol) → Repo (implements Protocol)
```

**After（3 层）**：
```
CLI (flow 函数) → Flows (业务类) → Data (具体实现)
```

---

## v0.1-v0.3（已完成功能）

### 核心功能

- ✅ 交易录入：`CreateTrade`
- ✅ 定投执行：`RunDailyDca` / `SkipDca`
- ✅ NAV 抓取：`FetchNavs`（单日 + 区间）
- ✅ 交易确认：`ConfirmTrades`（T+N 规则，延迟追踪）
- ✅ 日报推送：`MakeDailyReport`（Discord）
- ✅ 再平衡建议：`MakeRebalance`
- ✅ 状态摘要：`MakeStatusSummary`（市值/份额视图）

### 关键特性

- ✅ **交易日历**：`CalendarService` + `trading_calendar` 表
- ✅ **结算策略**：`SettlementPolicy`（卫兵/定价/计数日历）
- ✅ **定价日持久化**：`trades.pricing_date`（Schema v3）
- ✅ **确认延迟追踪**：显式标记超期交易，日报展示
- ✅ **严格 NAV 口径**：确认用定价日 NAV，日报仅用当日 NAV
- ✅ **展示日策略**：默认上一交易日，支持 `--as-of` 覆盖

> 详细规则见 `docs/settlement-rules.md`
> CLI 用法见 `docs/operations-log.md`

---

## v0.4+（待规划）

### 候选功能

- [ ] 周报 / 月报
- [ ] 历史导入（CSV 模板）
- [ ] 盘中估值（附加信息，非核心口径）
- [ ] 用户动作日志（为 AI 准备）
- [ ] 上下文快照（ContextSnapshot）
- [ ] 操作结果标注（Outcome）
- [ ] Platform & Account 抽象
- [ ] 冷却期机制

---

## v1.x+（AI 阶段，远期）

### 面向 AI 的数据准备（当前只做结构预留）

**意图标签**：
- 区分动作类型：定投执行 / 主动买入 / 再平衡 / 止损 / 分红再投
- 记录决策者：`human` / `Dca` / `AI_ASSISTED`（未来）

**上下文快照**：
- 组合状态：资产分布、风险指标、仓位、集中度
- 基金状态：近期涨跌、估值分位
- 账户状态：现金情况

**计划 vs 执行**：
- 计划层：定投计划、目标配置、再平衡规则
- 执行层：实际买卖及与计划的偏离

**数据视图**：
- `UserActionLog`：投资动作 + 标签 + 上下文
- `ContextSnapshot`：全局组合状态视图
- `Outcome`：事后结果标注（T+30/T+90 收益）

### AI 辅助功能（v1.x+）

- [ ] 自然语言接口（基于现有 Flows）
- [ ] AI 辅助定投/再平衡建议
- [ ] 个性化偏好与历史行为分析
- [ ] 复杂多市场/多币种支持

### 数据设计原则

- **原始信号可重建**：衍生字段可从原始数据重算
- **时点一致性**：快照基于"当时可见信息"，不用事后数据
- **主标签 + 扩展标签**：固定字段 + JSON 扩展
- **文本备注友好**：允许记录自然语言备注

---

## 技术债（持续改进）

### 交易日历

- [x] 基础日历表（v0.3 完成）
- [x] SettlementPolicy（v0.3 完成）
- [ ] 完整节假日覆盖（持续维护）
- [ ] 动态确认策略（v0.4+）

### NAV 覆盖

- [x] 严格口径（v0.2 完成）
- [x] 延迟追踪（v0.2.1 完成）
- [ ] 多日回填与重算（v0.4+）
- [ ] 外部数据源/缓存（v0.4+）

### 代码质量

- [x] 架构简化（v0.3.1 完成）
- [ ] 单元测试（v0.4+）
- [ ] 类型检查增强（v0.4+）
- [ ] 性能优化（按需）

---

> **当前阶段**：v0.3.1 架构简化已完成，准备进入 v0.4 功能增强阶段。
