# 开发决策记录

> 本文档记录关键架构与业务决策。
> 完整规则见 `docs/settlement-rules.md` / `docs/architecture.md`。

---

## 2025-12-07 限额公告 Facts 系统（v0.4.4）

**背景**：DCA 规则层需要"外部约束事实"输入，区分"金额变化是限额导致 vs 主动调整"。

**设计原则**：
- 规则层只记录"什么时候，这只基金被限额/暂停"，不做语义判断
- AI 基于限额事实 + 交易事实做综合分析

**最终方案**（经过 6 轮迭代）：
```
核心命令（3 个）：
1. check-status  ← AKShare 查询当前准确限额（主功能）
2. add           ← 手动录入特殊情况（兜底）
3. end           ← 结束限制记录（生命周期）

数据源：
- AKShare fund_purchase_em（主源）- 当前状态 + 准确限额，置信度=high
- 手动录入（兜底）- 特殊情况补充

未来扩展：
- v0.5：PDF 解析（GPT/NLP）构建历史时间线（详见 roadmap.md）
```

**核心实现**：
- Schema v15：新增 `fund_restrictions` 表
- `FundRestrictionFact` 模型 + `ParsedRestriction`（中间结果）
- `FundDataClient.get_trading_restriction()`（AKShare）+ `FundRestrictionRepo`
- Repo 方法：`add()` / `list_active_on()` / `list_by_period()` / `end_latest_active()`

**迭代历史**：
- Round 1-3：尝试公告标题解析 → 置信度低，删除
- Round 4：引入 AKShare → 获取准确限额（100元/日）
- Round 5-6：简化功能，删除 list/fetch 命令，聚焦核心

**教训**：
- 公告标题解析不稳定（金额在 PDF 正文中）
- 聚焦单一可靠数据源（AKShare）比多个模糊来源更有效

---

## 2025-12-05 领域命名规范落地（code-style）

**关键原则**：遵循"规则输出事实，AI 做解释"分工
- `*Draft` = 建议方案（内存结构，不入库）
- `*Check` = 验证结果（命中+偏差，不下结论）
- `*Flag` = 值得注意的点（仅标记）
- `*Facts` = 事实快照（供 AI 分析）
- `draft_*()` = 返回建议，不入库
- `scan_*()` = 只读，无副作用
- `backfill_*()` = 写操作，需谨慎

---

## 2025-12-05 DCA 回填逻辑校准（v0.4.3）

**问题**：原逻辑 `is_match = date_match AND amount_match` 属于语义判断，违反分工原则。

**调整**：
- 回填逻辑：`matched = date_match`（日期决定归属）
- 金额偏差只作为事实字段，不影响归属判断
- 同一天多笔买入时，只选金额最接近的一笔

**新增**：
- `FundDcaFacts` 模型 - DCA 事实快照（供 AI 分析）
- `build_dca_facts_for_batch()` Flow - 只读导出

---

## 2025-12-04 Import Batch 机制（v0.4.3）

**背景**：历史导入缺乏撤销和追溯能力。

**核心设计**：
- `import_batches` 表记录导入批次
- `trades.import_batch_id` + `trades.dca_plan_key` 字段
- 撤销机制：`WHERE import_batch_id = ?` 删除批次
- DCA 回填命令：`dca_plan backfill --batch-id <ID> [--mode apply]`

**Schema v14**：新增表 + 字段

---

## 2025-12 行为语义增强 & DCA 推断日历优化

**ActionLog v2**：
- 新增 `strategy` 字段（`dca` / `rebalance` / `none`）
- 真相层：trades/navs/dca_plans（底层事实）
- 故事层：action_log（行为时间线）

**DCA 推断日历集成**：
- 优先使用交易日历（日度≈1交易日，周度≈4-6，月度≈18-25）
- 无日历时回退自然日差（长假会降低识别率）
- 仍为只读分析，需手动确认

**Schema v13**：ActionLog 新增 `strategy` 字段

---

## 2025-12 CLI 标准化重构

统一 `src/cli/` 代码结构：
- 职责分离：`_parse_args()` / `_format_*()` / `_do_*()` / `main()`
- 数字标签注释：`# 1.` `# 2.` 标记步骤
- 统一日志：`log()`，返回码：0/4/5

---

## 2025-11 核心功能完善

**数据规范化**：
- 移除 `Trade.nav`，nav 已在 `navs` 表规范化存储
- 命名规范：Client（I/O）vs Service（业务逻辑）

**历史账单导入**：
- 支付宝账单解析（GBK 编码）
- 基金映射：`funds.alias` 匹配平台完整名称
- 自动抓取 NAV，计算份额，补录 ActionLog

**行为数据（action_log）**：
- 只记录用户决策行为
- Intent 枚举：`planned, impulse, opportunistic, exit, rebalance`

**业务闭环**：
- 月度定投修复：rule=31 在短月顺延到月末
- 手动确认：`trade confirm-manual` 处理 NAV 永久缺失
- 日历管理：统一 DB 后端，支持 exchange_calendars + Akshare 修补

**架构简化**：
- 目录重组：`jobs→cli`, `usecases→flows`, `adapters→data`
- 删除抽象层：移除 Protocol，改用 `@dependency` 装饰器
- 类名简化：`SqliteTradeRepo→TradeRepo`

> 早期版本决策见 git history。当前版本 v0.4.4+，详见 roadmap.md。
