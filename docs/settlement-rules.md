# 交易日历与确认规则（设计草稿）

## 现状（v0.1 实现）
- 函数：`src/core/trading/settlement.get_confirm_date`
- 规则：
  - A 股：T+1，若遇周末顺延到下一个周一。
  - QDII：T+2，若遇周末顺延到下一个周一/周二。
- 假设：
  - 仅处理周末，不处理法定节假日。
  - 不考虑基金类型差异、交易时间截点等复杂因素。

## 期望的目标行为（后续版本）
- 引入“交易日历表”，覆盖法定节假日与特殊交易日。
- 支持按市场/基金类型的差异化确认规则：
  - A 股普通基金：T+1，节假日顺延。
  - QDII：T+2，跨市场节假日并集顺延。
  - 未来可扩展其他市场/产品类型。
- 明确“定价日（pricing_date）”与“确认日”的区别：
  - 定价日用于份额计算（通常等于交易日；遇非交易日应取下一交易日）。
  - 确认日用于份额/资金到账展示（T+N 顺延）。
- 支持在确认流程中：优先用定价日 NAV，缺失时回退策略（上一/下一交易日）与重试机制（或标记异常）。

## 设计草稿
1) 交易日历表（建议新增表，可在 `docs/sql-schema-*` 后续版本里收录）
   - 字段示例：`day` (DATE, PK), `is_trading_day` (BOOLEAN), `market` (TEXT，如 A/QDII)，可扩展 `note`。
   - 数据来源：手工维护或从公开节假日接口导入。

2) 确认规则配置
   - 配置表（可放 `meta` 或独立表）：`market` -> `confirm_lag` (int)，`strategy` (如 `next_trading_day`)、`timezone`。
   - 每个基金可从其 `market` 继承，也可单独覆盖。

3) 计算逻辑（伪代码）
   - 输入：`market`, `trade_date`, 可选 `fund_code`。
   - 步骤：
     1. 读取 `confirm_lag`，初始确认日期 = `trade_date + lag`。
     2. 用交易日历求 `pricing_date = next_trading_day_or_self(trade_date)`。
     3. 用交易日历判断确认日期是否为交易日；若不是，按 `next_trading_day` 策略顺延。
     4. 返回 `confirm_date`；在确认时优先读取 `pricing_date` 的 NAV。

4) NAV 缺失与确认交互
   - 若确认日缺 NAV：标记该笔交易为“待确认NAV”状态，后续补齐 NAV 时再确认；或在日报/监控里提示缺失。

## 迁移路径
- v0.1 维持当前简化规则，不影响现有流程。
- v0.2 起草交易日历表结构与数据导入脚本；保留旧逻辑作为 fallback。
- 在 `TradeRepo` 增加“待确认NAV”状态处理时机（未来任务）。
