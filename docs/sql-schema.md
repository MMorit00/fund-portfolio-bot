# Database Schema

> **开发阶段说明**：
> - 本项目处于开发阶段，数据库可随时重建
> - 无需维护迁移脚本，直接运行 `SEED_RESET=1 PYTHONPATH=. python -m scripts.dev_seed_db`
> - Schema 由 `src/data/db/db_helper.py` 自动创建

## 当前版本

- Schema Version: **8** (SCHEMA_VERSION = 8)
- 最后更新: 2025-12-01

## 核心表结构

完整 DDL 见代码：`src/data/db/db_helper.py:_create_tables()`

### 主要表

| 表名 | 作用 | 关键字段 |
|------|------|---------|
| `funds` | 基金基础信息 | fund_code, name, asset_class, market, alias |
| `trades` | 交易记录 | id, fund_code, trade_date, pricing_date, confirm_date, confirmation_status |
| `navs` | 净值数据 | fund_code, day, nav |
| `trading_calendar` | 交易日历 | market, day, is_trading_day |
| `dca_plans` | 定投计划 | fund_code, amount, frequency, rule, status |
| `alloc_config` | 资产配置目标 | asset_class, target_weight, max_deviation |
| `action_log` | 用户行为日志 | id, action, actor, acted_at, trade_id, intent, note |
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

### action_log 表（v0.4 新增）

用户行为日志，记录每一次投资操作，为后续 AI 分析提供数据基础。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER | 主键 |
| `action` | TEXT | 动作类型：buy / sell / dca_skip / cancel |
| `actor` | TEXT | 执行者：human / system / dca |
| `acted_at` | TEXT | 发生时间（ISO datetime） |
| `trade_id` | INTEGER | 关联 trades.id（可空） |
| `intent` | TEXT | 意图标签：planned / impulse / opportunistic / exit / rebalance（可空） |
| `note` | TEXT | 人话备注（可空） |

**设计说明**：
- 只记录"发生了什么"，不存储快照或结果（需要时从 trades/navs 动态计算）
- `intent` 和 `note` 是给 AI 的关键信息，手动填写

**埋点范围**：

| 场景 | 是否记录 | action | actor | 说明 |
|------|----------|--------|-------|------|
| 手动买入/卖出 | ✅ | buy / sell | human | CLI `trade buy/sell` |
| DCA 自动执行 | ❌ | - | - | 系统行为，不记录 |
| 跳过定投 | ✅ | dca_skip | human | CLI `dca skip` |
| 取消交易 | ✅ | cancel | human | CLI `trade cancel`（v0.4.1+） |
| 交易确认 | ❌ | - | - | trades.status 已有 |
| 再平衡执行 | ❌ | - | - | 留到后续版本 |

**actor 含义**：
- `human`：用户通过 CLI 手动执行
- `system`：后台 job 自动执行（当前未使用）
- `dca`：定投计划触发（当前未使用）

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
