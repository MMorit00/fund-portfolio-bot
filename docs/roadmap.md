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
- ✅ **v0.3.1**：架构简化（目录重构、依赖注入）
- 🚧 **v0.3.2**：配置管理 CLI（补齐用户闭环，当前）
- 🔜 **v0.4+**：增强功能（周报/月报/历史导入）
- 🔮 **v1.x+**：AI 辅助决策（远期）

---

## v0.3.2（配置管理 CLI，🚧 进行中）

### 目标

补齐配置管理入口，让用户无需直接操作数据库即可完成初始化，形成完整的投资管理闭环。

### 背景问题

**当前缺陷**：
- ✅ 核心业务逻辑（Flow 层）：完整
- ✅ 数据模型（Schema v3）：完整
- ❌ CLI 用户入口：不完整（缺少配置管理）

**用户痛点**：
```sql
-- 用户必须手动写 SQL 才能开始使用系统
INSERT INTO funds VALUES (...);
INSERT INTO dca_plans VALUES (...);
INSERT INTO alloc_config VALUES (...);

-- 然后才能用 CLI
python -m src.cli.dca
python -m src.cli.confirm
```

### 完成内容

**Schema 更新**：
- `dca_plans` 表增加 `status` 字段（active/disabled）
- 支持禁用定投计划而不删除记录

**新增 Flow 函数**（`src/flows/config.py`）：
- `add_or_update_fund()` - 基金配置管理
- `list_funds()` - 查询基金列表
- `upsert_dca_plan()` - 定投计划管理
- `disable_dca_plan()` - 禁用定投计划
- `set_alloc_config()` - 资产配置目标设置
- `get_alloc_config()` - 查询配置目标

**新增 Flow 函数**（`src/flows/trade.py`）：
- `list_trades()` - 查询交易记录

**新增 CLI 命令**（P0 优先级）：
- `fund.py` - 基金配置（add/list/update）
- `dca_plan.py` - 定投计划（add/list/disable）
- `alloc.py` - 资产配置（set/show）
- `trade.py` - 手动交易（buy/sell/list）

**仓储层增强**：
- `DcaPlanRepo`: 新增 status 管理方法
- `AllocConfigRepo`: 新增 set/list 方法
- `TradeRepo`: 新增 list_by_status 方法
- `FundRepo`: 确保支持 upsert

### 用户体验改进

**改进前**：
```bash
# 必须手动写 SQL
sqlite3 data/portfolio.db "INSERT INTO funds ..."
```

**改进后**：
```bash
# 1. 配置基金
python -m src.cli.fund add --code 000001 --name "华夏成长" --class EQUITY_CN --market CN_A

# 2. 设置定投计划
python -m src.cli.dca_plan add --fund 000001 --freq monthly --day 1 --amount 1000

# 3. 设置资产配置目标
python -m src.cli.alloc set --class EQUITY_CN --target 0.60 --max-dev 0.05

# 4. 手动交易
python -m src.cli.trade buy --fund 000001 --amount 5000

# 5. 开始日常运维（已有）
python -m src.cli.dca
python -m src.cli.fetch_navs
python -m src.cli.confirm
python -m src.cli.report
```

### 完整业务闭环

```
配置管理阶段（新增）:
  fund add → dca_plan add → alloc set
    ↓
日常运维阶段（已有）:
  dca → trade buy/sell → fetch_navs → confirm → report
    ↓
决策调整阶段（已有）:
  report（再平衡建议） → trade buy/sell → 回到日常运维
```

### 验证标准

- ✅ 全新用户无需接触数据库即可完成初始化
- ✅ 所有配置支持 CLI 增删改查
- ✅ 保持架构分层清晰（CLI → Flow → Data）
- ✅ 所有 CLI 命令符合项目编码规范
- ✅ `ruff check --fix .` 全部通过

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

**✅ 依赖注入重构**（阶段 2）：
- Flow 层：业务类改为纯函数（8 个函数）
- 装饰器：`@dependency` 自动注入依赖
- 容器：`src/core/container.py` 集中管理 9 个依赖工厂
- CLI 层：一行调用 Flow 函数，无需手动实例化

**✅ 验证通过**：
- Ruff 检查：全部通过
- 功能测试：CLI 命令正常运行
- Schema 版本：保持 v3 不变
- 代码减少：~200 行样板代码

### 架构对比

**Before（4 层）**：
```
Jobs → DependencyContainer → UseCase (Protocol) → Repo (implements Protocol)
```

**After（3 层 + 依赖注入）**：
```
CLI → Flows (纯函数 + @dependency) → Data (通过装饰器注入)
         ↓
      Core (container + dependency)
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

## v0.4（行为 & 数据增强，规划中）

### 目标

**定位**："记得足够多、记得够规范"—— 在当前数据基础上补全行为数据结构，为未来所有分析功能（包括但不限于 AI）打好基础。

### 核心理念

行为数据基建不能拖到 v1.x 的理由：
- ✅ 未来所有 AI 相关功能都要依赖这套数据结构
- ✅ 行为和上下文的埋点，现在不做将来补数据很痛苦
- ✅ 即使短期不接 AI，也能支持非 AI 的行为复盘功能

### 完成内容

**P1 - 行为数据基建**（核心优先级）：
- [ ] **UserActionLog** 表（记录所有投资动作）
  - 动作类型：buy/sell/dca_execute/dca_skip/rebalance
  - 标签：来源（human/DCA/system）、意图（follow_plan/impulse/rebalance）
  - 关联：trade_id、context_snapshot_id
- [ ] **ContextSnapshot** 表（交易时点组合快照）
  - 组合状态：资产分布、总市值、偏离度
  - 基金状态：近期涨跌、持仓占比
  - 账户状态：可用现金（预留字段）
- [ ] **Outcome** 表（事后收益标注）
  - T+30/T+90 收益率
  - 与目标配置的偏离变化
  - 关联到 ActionLog

**P2 - 用户体验增强**（依赖 P1 数据）：
- [ ] **周报 / 月报**（重点展示行为统计而非仅收益）
  - 交易频率、类型分布
  - 定投执行率、额外加仓次数
  - 再平衡建议执行情况
- [ ] **历史导入**（CSV 模板 / Alipay 基础导入）
  - 补全历史交易数据
  - 自动关联 ActionLog 和 Snapshot
- [ ] **持仓详情视图**（单只基金时间维度表现）
  - 买入历史、持仓成本
  - 收益曲线、波动分析

**P3 - 可选增强**：
- [ ] 交互式配置向导（引导式初始化，如 v0.3.2 未完成）
- [ ] Platform & Account 抽象（多账户支持预留）

### 设计原则

**数据结构设计**：
- **原始信号可重建**：衍生字段可从原始数据重算
- **时点一致性**：快照基于"当时可见信息"，不用事后数据
- **主标签 + 扩展标签**：固定字段 + JSON 扩展字段
- **文本备注友好**：允许记录自然语言备注

**不做的事**（延后到 v0.5+）：
- ❌ 盘中估值（附加信息，非核心口径）
- ❌ 多数据源支持（偏可靠性增强，非能力质变）
- ❌ NAV 自动回填（可在不破坏数据结构下追加）

### 验证标准

- ✅ 每笔交易都能追溯到完整的行为上下文
- ✅ 支持"我什么时候容易冲动买入？"类查询
- ✅ 周报能展示行为模式而非仅数字
- ✅ Schema 设计为 AI 分析预留足够字段

---

## v0.5+（数据可靠性增强，待规划）

- [ ] 盘中估值（附加信息，非核心口径）
- [ ] 多数据源支持（天天基金等备份源）
- [ ] NAV 自动回填（检测缺失并补抓）
- [ ] 冷却期机制（防止频繁交易）
- [ ] 分红再投追踪
- [ ] 费率计算与展示

---

## v1.0（AI 行为复盘，远期）

### 目标

**定位**：不做交易建议，聚焦"行为复盘 + 自我约束建议"

### 核心场景

在完成 v0.4（UserActionLog + ContextSnapshot + Outcome）基础上，提供最小有用的 AI 功能：

**场景 1：行为模式分析**
```
用户问："我过去一年都在哪些时候容易冲动买入？"

AI 基于 ActionLog + Snapshot + Outcome 回答：
- 你有 X% 的买入发生在连续上涨第 N 天
- 其中 Y% 在 30 天后回撤超过 Z%
- 同时给出具体例子和"如果用某个冷却期规则会怎样"
```

**场景 2：计划执行复盘**
```
用户问："帮我看看定投计划执行得怎么样？"

AI 帮你：
- 统计每个 DCA 的执行率、额外加仓次数
- 标出最容易"手痒"的几个标的
- 对比"严格定投"vs"实际操作"的收益差异
```

**场景 3：自我约束建议**
```
用户问："我应该设置什么样的冷却期？"

AI 基于你的历史：
- 分析你的交易频率分布
- 找出"冲动交易"的时间间隔模式
- 给出个性化冷却期建议（而非一刀切）
```

### 完成内容

**核心功能**：
- [ ] **自然语言查询接口**（围绕现有 Flows + 行为数据）
  - 支持查询持仓、交易历史、配置偏离
  - 基于 ActionLog 的时间序列分析
- [ ] **行为模式分析**
  - 交易时机分析（市场状态 vs 交易行为）
  - 计划执行率统计（定投 vs 实际）
  - 偏离度与收益相关性分析
- [ ] **自我约束建议**
  - 个性化冷却期建议
  - 频繁调仓提醒
  - 与目标配置偏离预警

### 设计原则

**AI 定位**：
- ✅ 帮助用户理解自己的行为模式
- ✅ 基于用户自己的历史数据
- ✅ 不直接给出买卖建议（避免监管和伦理风险）
- ✅ 与产品"行为 + 策略 + 决策辅助"定位对齐

**技术路径**：
- 完全基于已有数据结构（ActionLog + Snapshot + Outcome）
- 不需要复杂外部因子
- 可以先用简单规则，再逐步引入模型

**不做的事**（延后到 v1.1+）：
- ❌ AI 辅助定投/再平衡建议（直接给操作建议）
- ❌ 多市场/多币种支持（数据复杂度增加）
- ❌ 预测性分析（涉及外部数据和模型风险）

### 验证标准

- ✅ 用户能用自然语言查询历史行为
- ✅ 能回答"我什么时候容易犯错？"
- ✅ 给出的建议基于用户自己的历史数据
- ✅ 不涉及具体标的推荐或买卖时机预测

---

## v1.1+（AI 进阶功能，待规划）

在 v1.0 基础上，根据实际使用情况逐步扩展：

- [ ] AI 辅助再平衡建议（基于历史执行效果）
- [ ] 多账户 / 多市场支持
- [ ] 外部因子引入（市场情绪、估值分位等）
- [ ] 更复杂的行为预测模型

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

## 开发路线图

```
v0.1 (MVP - 基础功能)
  ↓
v0.2 (严格 NAV 口径 + 延迟追踪)
  ↓
v0.3 (日历策略化 + Schema v3)
  ↓
v0.3.1 (架构简化 + 依赖注入) ✅ 已完成
  ↓
v0.3.2 (配置管理 CLI) 🚧 当前 - 形成完整用户闭环
  ↓
v0.4 (行为 & 数据增强) 🔜 下一步
  ├─ 行为数据基建 (UserActionLog / ContextSnapshot / Outcome)
  ├─ 周报/月报（行为统计）
  └─ 历史导入 + 持仓详情
  ↓
v0.5+ (数据可靠性增强)
  └─ 盘中估值 / 多数据源 / NAV 回填 / 冷却期
  ↓
v1.0 (AI 行为复盘)
  ├─ 自然语言查询
  ├─ 行为模式分析
  └─ 自我约束建议
  ↓
v1.1+ (AI 进阶功能)
  └─ 辅助建议 / 多账户 / 外部因子
```

**设计理念演进**：
- v0.1-v0.3：核心业务能力（交易 → 确认 → 报告）
- v0.3.1-v0.3.2：技术架构优化 + 用户体验闭环
- **v0.4：数据基建（为所有分析功能打基础）** ⬅️ 关键转折点
- v0.5+：可靠性增强（锦上添花）
- v1.0+：AI 能力（基于 v0.4 数据基建）

> **当前阶段**：v0.3.2 配置管理 CLI 开发中，完成后将进入 v0.4 行为数据基建阶段。
> **核心目标**：v0.4 是关键转折点，从"能用"到"记得足够多"，为未来所有分析功能（AI 和非 AI）打好基础。
