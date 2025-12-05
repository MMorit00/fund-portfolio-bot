# 开发决策记录

> 本文档记录关键架构与业务决策。
> 完整规则见 `docs/settlement-rules.md` / `docs/architecture.md`。

---

## 2025-12-05 领域命名规范落地（code-style 规范）

**背景**：代码评审指出现有 DCA 相关命名未遵循"规则输出事实，AI 做解释"分工原则，需对齐 `.claude/skills/code-style/SKILL.md` 的领域命名规范。
**关键原则**：
- `*Draft` = 建议方案，永不对应 DB 表，只是内存结构
- `*Check` = 单条数据针对规则的验证结果（命中+偏差+说明），不下结论
- `*Flag` = 规则识别的"值得注意"的点（异常、中断等），仅标记不定性
- `draft_*()` = 返回 `*Draft` 对象，不入库
- `scan_*()` = 只读，无副作用（Idempotent），可随意调用
- `backfill_*()` = **写操作**，修改 Truth Layer，需谨慎

---

## 2025-12-05 DCA 回填逻辑校准 + 事实快照（遵循"算法 vs AI 分工"原则）

### Phase 1：回填逻辑校准

**问题**：原 `_is_dca_match` 返回 `is_match = date_match AND amount_match`，属于语义判断，违反"规则只输出事实"原则。

**调整**：
- 函数重命名为 `_calc_dca_facts`，返回 `(date_match, amount_deviation, reason)`
- 回填逻辑：`matched = date_match`（日期决定归属）
- 金额偏差只作为事实字段（`BackfillMatch.amount_deviation`），不影响归属判断
- 同一天多笔买入时，只选金额最接近的一笔（定投每天最多执行一次）

### Phase 2：事实快照导出

**新增模型**：`FundDcaFacts` - 单只基金的 DCA 事实快照，供 AI 分析使用

```python
FundDcaFacts:
  - first_date / last_date      # 时间范围
  - first_amount / last_amount  # 金额变化趋势
  - amount_histogram: dict      # 金额分布 {'10.00': 19}
  - interval_histogram: dict    # 间隔分布 {1: 14, 3: 3}
  - avg_interval: float         # 平均间隔天数
```

**新增 Flow**：`build_dca_facts_for_batch(batch_id)` - 只读，不写库

**变更文件**：
- `src/core/models/dca_backfill.py` - BackfillMatch 增加字段 + FundDcaFacts 模型
- `src/flows/dca_backfill.py` - 回填逻辑调整 + build_dca_facts_for_batch Flow
- `src/cli/dca_plan.py` - infer --batch-id 参数 + _format_dca_facts 格式化
- `src/core/models/dca_infer.py` - DcaPlanCandidate.amount 文档说明"仅作参考建议"
- `docs/history-import.md` - DCA 回填规则说明改为"日期+同日唯一性决定归属，金额只作事实"

---

## 2025-12-04 Import Batch 机制（v0.4.3）

**背景**：历史导入功能（v0.4.2）缺乏撤销和追溯能力，需要一个"安全边界"机制。

### Phase 1：Batch 基础设施（✅ 已完成）

**核心设计**：
- `import_batches` 表记录导入批次（id, source, created_at, note）
- `trades.import_batch_id` + `trades.dca_plan_key` 字段
- 撤销机制：`WHERE import_batch_id = ?` 删除批次

**dca_plan_key 约定**：当前为 `fund_code`，未来若支持多计划升级为 `{fund_code}@{freq}@{rule}`

**Schema v14**：新增 `import_batches` 表，`trades` 增加 2 字段

### Phase 2：DCA 回填功能（✅ 已完成）

**命令**：`dca_plan backfill --batch-id <ID> [--mode apply]`

**核心设计**：日期匹配（daily/weekly/monthly）+ 金额偏差±10%，批量更新 `trades.dca_plan_key`。

**实现文件**：`src/flows/dca_backfill.py` / `src/cli/dca_plan.py`

---

## 2025-12 行为语义增强 & DCA 推断日历优化

**ActionLog v2 设计（已落地部分）**：引入 `strategy` 字段标记策略语境（`dca` / `rebalance` / `none`）
- 真相层：trades/navs/dca_plans 记录底层事实
- 故事层：action_log 记录行为时间线
- 简化实现：仅新增 strategy 字段，深度 DCA 字段留作 TODO

**Schema v13**：ActionLog 新增 `strategy TEXT` 字段，Flows 层埋点适配

**DCA 推断（dca_plan infer）日历集成**：
- 推断间隔时优先使用交易日历（trading_calendar + CalendarService）：
  - 日度：≈1 个交易日；
  - 周度：≈4–6 个交易日；
  - 月度：≈18–25 个交易日；
- 当日历服务不可用或缺失记录时，自动回退为自然日差：
  - 保持原有阈值（2/6–8/28–32），但春节/国庆等长假会降低 daily/weekly 识别率（偏保守漏报）；
- 推断仍为只读分析，不写入任何数据，所有候选计划需通过 `dca_plan add` 手动确认。

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
