# SQL Migrations v0.3

本版本聚焦“交易日历策略化与定价日持久化”。

## 变更摘要

- `schema_version` 升级为 3（由 `src/adapters/db/sqlite/db_helper.py` 写入）。
- trades 表新增列：`pricing_date TEXT NOT NULL`。
- 日历存取改为严格模式（缺失即报错）：`CalendarStore`。

## 迁移 SQL（从 v0.2 → v0.3）

注意：SQLite 对 `NOT NULL` 约束的增量迁移需要重建表；简化处理可先加可空列，再回填，再重建。

1) 快速路径（建议新装/重建库）

```sql
-- 备份后重建数据库（推荐在开发/测试环境）
-- 删除 data/portfolio.db 后由程序自动建表（包含 pricing_date 列）
```

2) 增量路径（保留历史数据）

```sql
-- 先加可空列
ALTER TABLE trades ADD COLUMN pricing_date TEXT;

-- 回填（伪代码：按策略重算）
-- for each trade: pricing_date = determine_pricing_date(trade_date, policy(market))
-- UPDATE trades SET pricing_date = :pricing WHERE id = :id;

-- 如需严格 NOT NULL，可重建 trades 表并复制数据（此处省略具体脚本）。
```

## 新/改动的逻辑

- 确认份额的 NAV 严格使用 `pricing_date`；确认用例在入库 `pricing_date` 缺失时会按策略回算，但推荐回填与强约束。
- `sync_calendar` 与 `patch_calendar` 均仅覆盖到各自数据源“最大已知日期”，避免未知未来被误写为休市。

## 回滚策略

- 如需回滚：
  - 保留 `pricing_date` 列不影响旧逻辑（忽略即可）。
  - CalendarStore 可切回 `SimpleTradingCalendar`（配置 `TRADING_CALENDAR_BACKEND=simple`）。

