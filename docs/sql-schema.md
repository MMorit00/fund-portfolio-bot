# Database Schema

> **开发阶段说明**：
> - 本项目处于开发阶段，数据库可随时重建
> - 无需维护迁移脚本，直接运行 `SEED_RESET=1 PYTHONPATH=. python -m scripts.dev_seed_db`
> - Schema 由 `src/data/db/db_helper.py` 自动创建

## 当前版本

- Schema Version: **13** (SCHEMA_VERSION = 13)
- 最后更新: 2025-12-03

## 核心表结构

完整 DDL 见代码：`src/data/db/db_helper.py:_create_tables()`

### 主要表

| 表名 | 作用 | 关键字段 |
|------|------|---------|
| `funds` | 基金基础信息 | fund_code, name, asset_class, market, alias |
| `fund_fee_items` | 基金费率（v0.4.4 新增） | fund_code, fee_type, charge_basis, rate, min_hold_days, max_hold_days |
| `trades` | 交易记录 | id, fund_code, trade_date, pricing_date, confirm_date, confirmation_status |
| `navs` | 净值数据 | fund_code, day, nav |
| `trading_calendar` | 交易日历 | market, day, is_trading_day |
| `dca_plans` | 定投计划 | fund_code, amount, frequency, rule, status |
| `alloc_config` | 资产配置目标 | asset_class, target_weight, max_deviation |
| `action_log` | 用户行为日志 | id, action, actor, source, acted_at, fund_code, target_date, trade_id, intent, note |
| `meta` | 元数据 | key, value (schema_version 等) |

## 重要字段说明

### trades 表关键字段

| 字段 | 类型 | 说明 | 引入版本 |
|------|------|------|---------|
| `pricing_date` | TEXT | 定价日，用于确认份额计算 | v0.3 |
| `confirmation_status` | TEXT | 确认状态：normal / delayed | v0.2 |
| `delayed_reason` | TEXT | 延迟原因：nav_missing / unknown | v0.2 |
| `delayed_since` | DATE | 首次检测到延迟的日期 | v0.2 |
| `external_id` | TEXT | 外部唯一标识（支付宝订单号等），用于历史导入去重 | v0.4.2 |

**业务规则**：见 `docs/settlement-rules.md`

### dca_plans 表关键字段

| 字段 | 类型 | 说明 | 引入版本 |
|------|------|------|---------|
| `frequency` | TEXT | 定投频率：daily / weekly / monthly | v0.1 |
| `rule` | TEXT | 定投规则（weekly: MON/TUE, monthly: 1..31） | v0.1 |
| `status` | TEXT | 状态：active / disabled | v0.3.2 |

**月度定投短月顺延**（v0.3.4+）：rule=29/30/31 在短月自动顺延到月末最后一天

### action_log 表（行为日志）

用户行为日志，记录每一次投资相关的决策行为，为后续 AI 分析提供数据基础。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER | 主键 |
| `action` | TEXT | 行为类型：buy / sell / dca_skip / cancel |
| `actor` | TEXT | 行为主体：human / assistant / system（当前仅使用 human） |
| `source` | TEXT | 行为来源：manual / import / automation / migration |
| `acted_at` | TEXT | 发生时间（ISO datetime） |
| `fund_code` | TEXT | 关联基金代码（可空） |
| `target_date` | TEXT | 行为针对的交易日/计划日（如定投日期，可空） |
| `trade_id` | INTEGER | 关联 trades.id（可空） |
| `intent` | TEXT | 意图标签：planned / impulse / opportunistic / exit / rebalance（可空） |
| `note` | TEXT | 人话备注（可空） |
| `strategy` | TEXT | 行为所属策略语境：dca / rebalance / none（可空） |

**设计说明**：
- 只记录“发生了什么”，不存储快照或结果（需要时从 trades/navs 动态计算）
- `intent` 和 `note` 是给 AI 的关键信息，手动填写或流程写入
- DCA 相关行为（如跳过某日定投）应尽量填写 `fund_code` + `target_date`，便于统计执行率

**埋点范围**：

| 场景 | 是否记录 | action | actor | source | 说明 |
|------|----------|--------|-------|--------|------|
| 手动买入/卖出 | ✅ | buy / sell | human | manual | 用户通过 CLI / 前端 / 聊天指令下单 |
| DCA 自动执行 | ❌ | - | - | - | 系统行为，不记录 |
| 跳过定投 | ✅ | dca_skip | human | manual | 用户主动跳过某日定投 |
| 取消交易 | ✅ | cancel | human | manual | 用户主动取消 pending 交易 |
| 导入历史交易 | ✅ | buy / sell | human | import | history_import Flow 自动补录 |
| 交易确认 | ❌ | - | - | - | trades.status 已有 |
| 再平衡执行 | ❌ | - | - | - | 留到后续版本 |

**actor 含义**：
- `human`：用户通过任意交互方式触发（CLI / 前端按钮 / 聊天指令等）
- `assistant`：AI 助手基于策略自动执行（预留，当前未使用）
- `system`：后台 job 或硬规则任务（预留，当前未使用）

**TODO（未来扩展）**：
- 引入 ContextSnapshot / Outcome 等表，通过 action_log.id 建立一对一关联；
- 如需多账户/多组合，考虑在 action_log 增加 account_id/portfolio_id 字段。

### ActionLog v2 演进规划（草案）

**当前版本**（v0.4.3，Schema v13）：已新增 `strategy` 字段

```sql
-- v0.4.3 已实现
ALTER TABLE action_log ADD COLUMN strategy TEXT;
-- 取值：'dca' / 'rebalance' / 'none'
-- 用途：标记行为的策略语境
```

**未来版本**（v0.x TODO）：深度 DCA 归属字段

以下字段作为未来演进方向，当前**不实现**：

```sql
-- ActionLog 深度 DCA 归属（TODO）
ALTER TABLE action_log ADD COLUMN is_dca_execution INTEGER;
-- 是否为 DCA 执行（0/1/NULL）

ALTER TABLE action_log ADD COLUMN dca_plan_key TEXT;
-- 定投计划标识（如 "001551@monthly@10"）

ALTER TABLE action_log ADD COLUMN dca_tag_source TEXT;
-- DCA 归属来源：'auto_run' / 'import_infer' / 'manual'
```

```sql
-- Trade 层 DCA 归属（TODO）
ALTER TABLE trades ADD COLUMN dca_plan_key TEXT;
-- 交易归属的定投计划

ALTER TABLE trades ADD COLUMN dca_tag_source TEXT;
-- DCA 归属来源标记
```

**字段分类**：

| 字段 | 类型 | 状态 |
|------|------|------|
| `strategy` | 解释字段 | v0.4.3 实现 |
| `is_dca_execution` | 解释字段 | TODO |
| `dca_plan_key` | 解释字段 | TODO |
| `dca_tag_source` | 解释字段 | TODO |
| action/actor/source/acted_at/trade_id | 事实字段 | 已有（只能 append-only） |

**实现时机**：
- 需要"DCA 执行率统计"（实际执行数 / 计划执行数）
- 需要"导入回填 DCA 归属"（将历史交易标记为定投）
- 需要"DCA 归因分析"（区分自动执行 vs 导入推断 vs 手动标记）

**设计原则**：
- **事实字段**：只能新增，不可修改（append-only）
- **解释字段**：允许后续回填/修正，不改变真相层数据
- 回填操作只更新解释字段，不修改 action/actor/source/acted_at 等事实字段

### fund_fee_items 表（v0.4.4 新增）

基金费率信息独立表，支持多种费率类型和赎回费阶梯。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER | 主键 |
| `fund_code` | TEXT | 基金代码（外键） |
| `fee_type` | TEXT | 费率类型：management / custody / service / purchase / purchase_discount / redemption |
| `charge_basis` | TEXT | 收费方式：annual（年化）/ transaction（单笔） |
| `rate` | TEXT | 费率（百分比，如 0.50 表示 0.50%） |
| `min_hold_days` | INTEGER | 赎回费阶梯用：最小持有天数（含），其他类型为 NULL |
| `max_hold_days` | INTEGER | 赎回费阶梯用：最大持有天数（不含），NULL 表示无上限 |

**fee_type 枚举说明**：

| fee_type | 含义 | charge_basis | min/max_hold_days |
|----------|------|--------------|-------------------|
| management | 管理费（年化） | annual | NULL |
| custody | 托管费（年化） | annual | NULL |
| service | 销售服务费（年化） | annual | NULL |
| purchase | 申购费（原价） | transaction | NULL |
| purchase_discount | 申购费（折扣后） | transaction | NULL |
| redemption | 赎回费（按持有天数） | transaction | 使用 min/max |

**赎回费阶梯示例**：

```
持有 0-7 天:    1.50%
持有 7-365 天:  0.50%
持有 365-730 天: 0.25%
持有 ≥730 天:   0.00%
```

**Repo 方法**：
- `FundFeeRepo.get_fees(fund_code)` - 获取 FundFees 聚合对象
- `FundFeeRepo.upsert_fees(fund_code, fees)` - 全量更新费率
- `FundFeeRepo.has_operating_fees(fund_code)` - 检查是否已有运作费率
- `FundFeeRepo.get_redemption_fee(fund_code, hold_days)` - 获取指定持有天数的赎回费率

### trading_calendar 表

用于维护不同市场的交易日信息（节假日/临时休市等）。

**初始化方式**（v0.3.4+）：
```bash
# 使用 exchange_calendars 注油
python -m src.cli.calendar sync --market CN_A --from 2020-01-01 --to 2025-12-31

# 使用 Akshare 修补
python -m src.cli.calendar patch-cn-a --back 30 --forward 365

# 或从 CSV 导入
python -m src.cli.calendar refresh --csv data/trading_calendar.csv
```

## Schema 变更流程

开发阶段无需增量迁移，直接重建即可：

```bash
# 1. 修改 DDL
vim src/data/db/db_helper.py

# 2. 删除旧库
rm data/portfolio.db

# 3. 重建数据库
SEED_RESET=1 PYTHONPATH=. python -m scripts.dev_seed_db

# 4. 记录决策
# 在 docs/coding-log.md 记录为什么改 schema
```

## Schema 演进历史

> 详细决策原因见 `docs/coding-log.md`

- **v0.1** (2025-11-15): 初始 schema（funds/trades/navs/dca_plans/alloc_config）
- **v0.2** (2025-11-18): 引入 `trading_calendar` 表，`trades` 表增加确认延迟追踪字段
- **v0.3** (2025-11-19): `trades` 表增加 `pricing_date` 字段，持久化定价日
- **v0.3.2** (2025-11-22): `dca_plans` 表增加 `status` 字段（active/disabled）
- **v0.3.4** (2025-11-26): 月度定投短月顺延（逻辑变更，无 schema 变更）
- **v0.4** (2025-11-26): 新增 `action_log` 表，用户行为日志
- **v0.4.2** (2025-11-30): `funds` 表增加 `alias` 字段，`trades` 表增加 `external_id` 字段（历史导入去重）
- **v0.4.2+** (2025-12-01): 移除 `trades` 表的 `nav` 字段（数据规范化，nav 归一化存储于 navs 表）
- **v0.4.3** (2025-12-02): `funds` 表增加费率字段（management_fee, custody_fee, service_fee, purchase_fee, purchase_fee_discount）
- **v0.4.4** (2025-12-02): 费率模型重构，新增 `fund_fee_items` 表，支持赎回费阶梯；`funds` 表移除费率字段

## 何时需要迁移文档？

**当满足以下任一条件时**，再引入迁移脚本和详细迁移文档：

- ✅ 进入生产环境（有真实用户数据需要保护）
- ✅ 数据库大小 > 10MB（重建成本过高）
- ✅ 有外部贡献者需要升级本地环境
- ✅ 多环境部署（开发/测试/生产）

**当前状态**：纯开发阶段，以上条件均不满足 ❌

---

## v0.4.2 实现（历史导入支持）

> **状态**：✅ 已完成

### funds 表扩展（✅ 已实现）

```sql
-- 新增 alias 字段：存储支付宝/天天基金等平台的完整基金名称
ALTER TABLE funds ADD COLUMN alias TEXT;
```

**用途**：历史账单导入时，根据 `alias` 匹配基金代码

**示例**：

| fund_code | name | alias |
|-----------|------|-------|
| 016057 | 嘉实纳指A | 嘉实纳斯达克100ETF联接(QDII)A |
| 001551 | 天弘纳指C | 天弘纳斯达克100指数(QDII)C |

**Repo 方法**：
- `FundRepo.find_by_alias(alias)` - 通过 alias 查找基金
- `FundRepo.update_alias(fund_code, alias)` - 更新基金的 alias

### trades 表扩展（✅ 已实现）

```sql
-- 新增 external_id 字段：外部流水号，用于去重
ALTER TABLE trades ADD COLUMN external_id TEXT UNIQUE;
```

**用途**：
- `external_id`：存储支付宝交易号/Alipay 订单号，防止重复导入
- 数据库级唯一约束（UNIQUE）：自动防重

**去重机制**：
- 首次导入：写入 `external_id`
- 重复导入：UNIQUE 约束触发，TradeRepo 捕获并跳过

### 详细设计

见 `docs/history-import.md`
