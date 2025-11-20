# Database Schema (开发版)

> **开发阶段说明**：
> - 本项目处于开发阶段，数据库可随时重建
> - 无需维护迁移脚本，直接运行 `SEED_RESET=1 python -m scripts.dev_seed_db`
> - Schema 由 `src/adapters/db/sqlite/db_helper.py` 自动创建

## 当前版本

- Schema Version: **3** (SCHEMA_VERSION = 3)
- 最后更新: 2025-11-19

## 核心表结构

完整 DDL 见代码：`src/adapters/db/sqlite/db_helper.py:_create_tables()`

### 主要表

| 表名 | 作用 | 关键字段 |
|------|------|---------|
| `funds` | 基金基础信息 | fund_code, name, asset_class, market |
| `trades` | 交易记录 | id, fund_code, trade_date, pricing_date, confirm_date, confirmation_status |
| `navs` | 净值数据 | fund_code, day, nav |
| `trading_calendar` | 交易日历 | market, day, is_trading_day |
| `dca_plans` | 定投计划 | fund_code, target_amount, frequency |
| `alloc_config` | 资产配置目标 | asset_class, target_weight, max_deviation |
| `meta` | 元数据 | key, value (schema_version 等) |

## 重要字段说明

### trades 表关键字段 (v0.3)

| 字段 | 类型 | 说明 | 引入版本 |
|------|------|------|---------|
| `pricing_date` | TEXT | 定价日，用于确认份额计算 | v0.3 |
| `confirmation_status` | TEXT | 确认状态：normal / delayed | v0.2 |
| `delayed_reason` | TEXT | 延迟原因：nav_missing / unknown | v0.2 |
| `delayed_since` | DATE | 首次检测到延迟的日期 | v0.2 |

**业务规则**：见 `docs/settlement-rules.md`

### trading_calendar 表 (v0.2)

用于维护不同市场的交易日信息（节假日/临时休市等）。

**初始化方式**：
```bash
python scripts/import_trading_calendar.py data/trading_calendar/a_shares.csv
```

## Schema 变更流程

开发阶段无需增量迁移，直接重建即可：

```bash
# 1. 修改 DDL
vim src/adapters/db/sqlite/db_helper.py

# 2. 删除旧库
rm data/portfolio.db

# 3. 重建数据库
SEED_RESET=1 python -m scripts.dev_seed_db

# 4. 记录决策
# 在 docs/coding-log.md 记录为什么改 schema
```

## Schema 演进历史

> 详细决策原因见 `docs/coding-log.md`

- **v0.1** (2025-11-15): 初始 schema（funds/trades/navs/dca_plans/alloc_config）
- **v0.2** (2025-11-18): 引入 `trading_calendar` 表，`trades` 表增加确认延迟追踪字段
- **v0.3** (2025-11-19): `trades` 表增加 `pricing_date` 字段，持久化定价日

## 何时需要迁移文档？

**当满足以下任一条件时**，再引入迁移脚本和详细迁移文档：

- ✅ 进入生产环境（有真实用户数据需要保护）
- ✅ 数据库大小 > 10MB（重建成本过高）
- ✅ 有外部贡献者需要升级本地环境
- ✅ 多环境部署（开发/测试/生产）

**当前状态**：纯开发阶段，以上条件均不满足 ❌
