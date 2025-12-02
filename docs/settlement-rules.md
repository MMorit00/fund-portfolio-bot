# 交易日历与确认规则

> **本文档是交易日历、确认规则、NAV 策略与再平衡规则的权威来源。**
> 若其他文档与本文描述存在不一致，以本文件为准。

---

## 1. 确认规则（Confirm 逻辑）

### 定价日计算（pricing_date）

- **定价日** = `calendar.next_trading_day_or_self(trade_date)`
- 含义：交易提交日当天若是交易日，则当日定价；若是休市日，顺延到下一交易日定价
- 入库：`trades.pricing_date` 字段持久化，确认时严格按该日 NAV

### 确认日计算（confirm_date）

- **确认日** = `calendar.next_trading_day(pricing_date, offset=settle_lag)`
- `settle_lag` 按市场类型：
  - A 股（CN_A）：1（T+1）
  - 美股 QDII（US_NYSE）：2（T+2）

### 使用的日历

- **CalendarService**：从 `trading_calendar` 表读取，提供 `is_open` / `next_open` / `shift` 方法
- **数据源管理**（v0.3.4+）：
  - 注油：`calendar sync`（exchange_calendars，提供基础日历骨架）
  - 修补：`calendar patch-cn-a`（Akshare + 新浪财经，修正临时调休）
  - 离线：`calendar refresh`（CSV 导入）

### QDII 特殊规则（SettlementPolicy）

QDII 基金使用三层日历组合（字段名对应 SettlementPolicy）：
- **guard_calendar_id**：`CN_A`（卫兵日历，过滤国内节假日）
- **pricing_calendar_id**：`US_NYSE`（定价日历，决定 pricing_date）
- **settlement_calendar_id**：`US_NYSE`（计数日历，决定 T+N 如何数）
- **settlement_lag**：2

示例：国庆期间下单（2025-10-01）
- `CN_A` 卫兵放行日：2025-10-09（10-01..10-08 休市）
- `pricing_date`：2025-10-09（`US_NYSE` 下一交易日或当日）
- `confirm_date`：2025-10-13（`US_NYSE` 交易日 +2）

---

## 2. NAV 策略

### 确认用 NAV（confirm 命令）

- **仅使用定价日 NAV**：从 `navs` 表读取 `trades.pricing_date` 对应的 NAV
- **缺失或 ≤ 0 时**：标记延迟状态（见下节），每日重试
- **不做任何回退**：不用"上一交易日 NAV"或"下一交易日 NAV"

### 报表用 NAV（report / rebalance 命令）

- **仅使用展示日 NAV**：`--as-of` 参数指定（默认上一交易日）
- **缺失或 ≤ 0 时**：该基金不计入当日市值与权重，在"NAV 缺失"区块列出
- **不做回退**：报告文案提示"总市值可能低估"
- **兜底视图**：份额视图（`--mode shares`）不依赖 NAV

### NAV 抓取（fetch_navs / fetch_navs_range）

- **严格口径**：只抓指定日，不做"最近交易日回退"
- **幂等 upsert**：按 `(fund_code, day)` 幂等写入
- **失败汇总**：结束时统一打印失败清单

---

## 3. 确认延迟处理

### 场景

交易按 T+N 规则已到确认日，但无法获取定价日 NAV 时，系统会标记为"延迟"。

### 处理策略

1. **不修改 `confirm_date`**：理论确认日保持不变（用于追踪延迟时长）
2. **显式标记延迟**：
   - `confirmation_status` 设为 `delayed`
   - `delayed_reason` 记录原因（`nav_missing`）
   - `delayed_since` 记录首次检测到延迟的日期
3. **每日重试**：`confirm` 命令每天重新检查，NAV 可用时自动确认
4. **手动确认**（v0.3.4+）：NAV 持续缺失时，可用 `trade confirm-manual` 手动确认

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
                                          └─ 每日重试或手动确认
```

### 用户可见反馈

在日报的"交易确认情况"板块中：
- 显示延迟天数（`today - confirm_date`）
- 显示延迟原因
- 给出建议：
  - ≤2 天：等待 1-2 个工作日
  - >2 天：建议到支付宝核查，或使用 `trade confirm-manual` 手动确认

---

## 4. 再平衡规则

### 阈值来源

- 使用 `alloc_config.max_deviation`（按资产类别配置）
- 未配置时使用默认 5% 阈值（0.05）

### 触发条件

- 当 `|实际权重 - 目标权重| > 阈值` 时，给出"增持/减持"建议
- 否则标注为"正常（hold）"

### 建议金额算法（v0.3.3）

- **资产类别级别**：`建议金额 = 总市值 × |偏离| × 50%`（渐进式）
- **基金级别**：
  - 买入策略：优先推荐持仓较小的基金（平均化持仓）
  - 卖出策略：优先推荐持仓较大的基金（渐进式减仓）
  - 金额分配：平均分配到符合策略的基金

### 口径与限制

- **权重与总市值**：与"市值版日报"一致，仅使用展示日 NAV、已确认份额
- **不考虑**：交易成本、最小申赎份额、税费
- **粒度**：资产类别 + 基金级别（v0.3.3+）

---

## 5. 月度定投规则（v0.3.4+）

### 短月顺延

- 月度定投 rule=29/30/31 在短月自动顺延到月末最后一天
- 示例：
  - rule=31 在 2 月 28 日（非闰年）触发
  - rule=31 在 4 月 30 日（30 天月份）触发
  - rule=31 在 3 月 31 日（31 天月份）触发

---

## 运维操作示例

见 `docs/operations-log.md`（日常命令、补录 NAV、处理延迟等）。
