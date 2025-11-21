# 交易日历与确认规则

> **本文档是交易日历、确认规则、NAV 策略与再平衡规则的权威来源。**
> 若其他文档（architecture/roadmap/log 等）与本文件描述存在不一致，以本文件为准。

---

## 1. 确认规则（Confirm 逻辑）

### 定价日计算（pricing_date）

- **定价日** = `calendar.next_trading_day_or_self(trade_date)`
- 含义：交易提交日当天若是交易日，则当日定价；若是休市日，顺延到下一交易日定价
- 入库：`trades.pricing_date` 字段持久化，确认时严格按该日 NAV

### 确认日计算（confirm_date）

- **确认日** = `calendar.next_trading_day(pricing_date, offset=settle_lag)`
- `settle_lag` 按市场类型：
  - A 股：1（T+1）
  - QDII：2（T+2）
- 不做基金级覆盖（未来可扩展）

### 使用的日历

- **CalendarProtocol**：统一日历接口，提供 `is_open` / `next_open` / `shift` 方法
- **DbCalendarService**：从 `trading_calendar` 表读取，严格模式（缺失即报错）
- **数据源**：
  - 注油：`exchange_calendars`（基础日历，到"日历最大已知日期"）
  - 修补：`Akshare`（新浪，在线覆盖，到"数据源最大已知日期"）

### QDII 特殊规则（SettlementPolicy）

QDII 基金使用三层日历组合：
- **guard_calendar**：`CN_A`（卫兵日历，过滤国内节假日）
- **pricing_calendar**：`US_NYSE`（定价日历，决定 pricing_date）
- **count_calendar**：`US_NYSE`（计数日历，决定 T+N 如何数）
- **settle_lag**：2

示例：国庆期间下单（2025-10-01）
- `CN_A` 卫兵放行日：2025-10-09（10-01..10-08 休市）
- `pricing_date`：2025-10-09（`US_NYSE` 下一交易日或当日）
- `confirm_date`：2025-10-13（`US_NYSE` 交易日 +2）

---

## 2. NAV 策略

### 确认用 NAV（ConfirmPendingTrades）

- **仅使用定价日 NAV**：从 `navs` 表读取 `trades.pricing_date` 对应的 NAV
- **缺失或 ≤ 0 时**：直接跳过，保留为 `pending`，标记延迟状态（见下节），后续可重试
- **不做任何回退**：不用"上一交易日 NAV"或"下一交易日 NAV"

### 报表/状态视图用 NAV（日报、status）

- **仅使用展示日 NAV**：`day = --as-of` 参数指定（默认上一交易日）
- **缺失或 ≤ 0 时**：该基金不计入当日市值与权重，在"NAV 缺失"区块列出基金代码
- **不做回退**：不用"最近交易日 NAV"；报告文案提示"总市值可能低估"
- **兜底视图**：份额视图（`--mode shares`）不依赖 NAV，可在 NAV 不全时使用

### NAV 抓取（fetch_navs / fetch_navs_range）

- **严格口径**：只抓指定日，不做"最近交易日回退"
- **幂等 upsert**：按 `(fund_code, day)` 幂等写入 `navs` 表
- **失败汇总**：Job 结束时统一打印失败清单

---

## 3. 确认延迟处理

### 场景

当交易按 T+N 规则已到理论确认日，但无法获取定价日 NAV 数据时，系统会标记为"延迟"。

### 处理策略

1. **不修改 `confirm_date`**：理论确认日保持不变（用于追踪延迟时长）
2. **显式标记延迟**：
   - `confirmation_status` 设为 `delayed`
   - `delayed_reason` 记录延迟原因（`nav_missing` / `unknown`）
   - `delayed_since` 记录首次检测到延迟的日期
3. **每日重试**：`ConfirmPendingTrades` job 每天会重新检查，一旦 NAV 数据可用立即确认

### 状态转换图

```
pending (normal)
    │
    │  today >= confirm_date?
    ├─── NO ──────────────────────────→ 保持 pending (normal)
    │
    └─── YES
         │
         │  pricing_date NAV 可用？
         ├─── YES ─────────────────────→ confirmed (normal)
         │                                 ✓ 份额入库
         │                                 ✓ status 清空
         │
         └─── NO ──────────────────────→ pending (delayed)
                                          ├─ delayed_reason = nav_missing
                                          ├─ delayed_since = today
                                          └─ 每日重试，NAV 可用后自动确认
```

### 延迟原因分类

- `nav_missing`：本地 `navs` 表中无对应 `pricing_date` 的 NAV 数据
  - 可能原因：基金公司延后披露、数据源同步延迟、节假日调整
- `unknown`：其他未分类原因

### 用户可见反馈

在每日报告的"交易确认情况"板块中：
- 显示延迟天数（`today - confirm_date`）
- 显示延迟原因
- 给出建议：
  - ≤2 天：等待 1-2 个工作日
  - >2 天：建议到支付宝核查订单状态

---

## 4. 再平衡规则

### 阈值来源

- 优先使用 `alloc_config.max_deviation`（按资产类别配置）
- 未配置时使用默认 5% 阈值（0.05）

### 触发条件

- 当 `|实际权重 - 目标权重| > 阈值` 时，给出"增持/减持"建议
- 否则标注为"观察（hold）"

### 建议金额算法

- `建议金额 = 总市值 × |偏离| × 50%`（渐进式，保守），仅用于提示
- 正偏离（超配）→ 减持；负偏离（低配）→ 增持

### 口径与限制

- **权重与总市值与"市值版日报"一致**：仅使用展示日 NAV、已确认份额、不回退
- **不考虑**：交易成本、最小申赎份额、税费
- **粒度**：只到资产类别，不拆分到具体基金层面

---

## 5. Schema 字段对应

### trades 表关键字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `pricing_date` | TEXT | 定价日，用于确认份额计算（NOT NULL） |
| `confirm_date` | TEXT | 理论确认日（T+N） |
| `confirmation_status` | TEXT | 确认状态：`normal` / `delayed` |
| `delayed_reason` | TEXT | 延迟原因：`nav_missing` / `unknown` |
| `delayed_since` | DATE | 首次检测到延迟的日期 |

### trading_calendar 表

| 字段 | 类型 | 说明 |
|------|------|------|
| `market` | TEXT | 市场标识（如 `CN_A` / `US_NYSE`） |
| `day` | DATE | 日期（YYYY-MM-DD） |
| `is_trading_day` | INTEGER | 是否交易日（0/1） |

> Schema 完整定义见 `docs/sql-schema.md`（开发阶段可随时重建）。

---

## 6. 运维操作示例

见 `docs/operations-log.md`（日常 Job 调度、补录 NAV、处理延迟等）。
