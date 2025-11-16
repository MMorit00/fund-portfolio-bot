# SQL Migrations v0.2（设计草稿）

本版本主要引入“交易日历 + 确认策略”的结构化设计，但不强制迁移现有表结构。以下为未来可能的迁移草图，便于 v0.3 起落地。

- 保持现有表不变：`funds` / `trades` / `navs` / `dca_plans` / `alloc_config` / `meta`
- 继续在创建交易时写入 `trades.confirm_date`（按当时规则计算）

## 新增表：trading_calendar（可选）

- 作用：维护不同市场的交易日信息（节假日/临时休市等），供确认/定价计算使用。

表结构（草案）：

- `market` TEXT NOT NULL  — 例如 `A` / `QDII`
- `day` DATE NOT NULL     — `YYYY-MM-DD`
- `is_trading_day` INTEGER NOT NULL  — 0/1 布尔
- `note` TEXT             — 可选备注
- PRIMARY KEY (`market`, `day`)

说明：
- v0.2 实现中采用 `SimpleTradingCalendar`（仅周末非交易日），不依赖该表。
- v0.3 可新增数据导入任务（脚本/接口）维护该表；`get_confirm_date` 与用例无缝替换为“基于 DB 的日历”。

## 兼容性说明

- 历史 `trades.confirm_date` 为“写入时的规则结果”，回溯规则时不强制更新老记录。
- v0.2 起，用例 `ConfirmPendingTrades` 对 NAV 的选择为：仅使用定价日 NAV；若缺失/<=0，则跳过并待后续重试。
- 注：历史记录中的 `trades.nav` 可能保留旧规则下的确认用净值（含确认日 NAV），v0.2 不回溯修正。
