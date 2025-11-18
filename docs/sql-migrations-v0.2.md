# SQL Migrations v0.2（设计草稿）

本版本主要引入“交易日历 + 确认策略”的结构化设计，但不强制迁移现有表结构。以下为未来可能的迁移草图，便于 v0.3 起落地。

- 保持现有表不变：`funds` / `trades` / `navs` / `dca_plans` / `alloc_config` / `meta`
- 继续在创建交易时写入 `trades.confirm_date`（按当时规则计算）

## 新增表：trading_calendar（v0.2 正式表）

- 作用：维护不同市场的交易日信息（节假日/临时休市等），供确认/定价计算使用。

表结构：

```sql
CREATE TABLE IF NOT EXISTS trading_calendar (
    market TEXT NOT NULL,           -- 'A' / 'QDII'
    day DATE NOT NULL,              -- 'YYYY-MM-DD'
    is_trading_day INTEGER NOT NULL,  -- 0/1 布尔
    PRIMARY KEY (market, day)
);
```

说明：
- v0.2 统一使用 `SqliteTradingCalendar`（基于此表）
- 缺失行时直接抛异常，不做 weekday 兜底（确保数据准确性）
- 初始化方式：运行 `python scripts/import_trading_calendar.py`（默认导入 `data/trading_calendar_A_2020-2030.csv`）

## trades 表扩展 - 确认延迟追踪（v0.2.1）

**新增字段**：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `confirmation_status` | TEXT | 确认状态：`normal`（正常）/ `delayed`（延迟），默认 `normal` |
| `delayed_reason` | TEXT | 延迟原因：`nav_missing`（NAV数据缺失）/ `unknown`（原因未明），仅 `delayed` 时有值 |
| `delayed_since` | DATE | 首次检测到延迟的日期（即首次 `today >= confirm_date` 且 NAV 缺失的日期） |

**迁移 SQL**：

```sql
-- v0.2.1: 为 trades 表添加确认延迟追踪字段
ALTER TABLE trades ADD COLUMN confirmation_status TEXT DEFAULT 'normal';
ALTER TABLE trades ADD COLUMN delayed_reason TEXT;
ALTER TABLE trades ADD COLUMN delayed_since DATE;
```

**字段语义**：

- `confirm_date` 仍然是"理论确认日"（由 TradingCalendar 根据 `pricing_date + settle_lag` 算出），**不因延迟而修改**
- `confirmation_status`：
  - `normal`：正常确认（已确认 or 未到确认日）
  - `delayed`：已到/超过理论确认日，但 NAV 数据缺失，无法确认
- `delayed_reason`：
  - `nav_missing`：本地 `navs` 表中无对应定价日的 NAV 数据
  - `unknown`：其他未分类原因（v0.2 暂不细分，v0.3+ 可扩展 `fund_event` 等）
- `delayed_since`：用于追踪延迟时长，方便日报提示"已延迟 X 天"

## 兼容性说明

- 历史 `trades.confirm_date` 为“写入时的规则结果”，回溯规则时不强制更新老记录。
- v0.2 起，用例 `ConfirmPendingTrades` 对 NAV 的选择为：仅使用定价日 NAV；若缺失/<=0，则跳过并待后续重试。
- 注：历史记录中的 `trades.nav` 可能保留旧规则下的确认用净值（含确认日 NAV），v0.2 不回溯修正。
