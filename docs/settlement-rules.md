# 交易日历与确认规则（v0.2）

## 现状（v0.1 实现）
- 函数：`src/core/trading/settlement.get_confirm_date`
- 规则：
  - A 股：T+1，若遇周末顺延到下一个周一。
  - QDII：T+2，若遇周末顺延到下一个周一/周二。
- 假设：
  - 仅处理周末，不处理法定节假日。
  - 不考虑基金类型差异、交易时间截点等复杂因素。

## v0.2 规则（已实现）
- 接口：`get_confirm_date(market, trade_date, calendar)`（纯函数），`TradingCalendar`（协议）
- 市场范围：仅 `A` 与 `QDII`
- 确认 lag：`A=1`、`QDII=2`（不做基金级覆盖）
- 定价日：`pricing_date = calendar.next_trading_day_or_self(trade_date)`
- 确认日：`confirm_date = calendar.next_trading_day(pricing_date, offset=lag)`
- 交易日历实现：`SimpleTradingCalendar`（仅周末为非交易日，不含节假日表）
- NAV 使用（确认用例）：仅取 `pricing_date` 的官方净值；若缺失或 `<=0`，则跳过待重试

差异说明：
- 相比 v0.1（基于 `trade_date + lag` 再周末顺延），当“下单日在周末”时：
  - `A` 基金确认日落在下周二（更符合“定价日=T+1”的实务口径）；
  - `QDII` 基金确认日随之后移（定价日+2）。

接口落点：
- `src/core/trading/calendar.py` 定义 `TradingCalendar` 与 `SimpleTradingCalendar`
- `src/core/trading/settlement.py` 定义新版 `get_confirm_date`
- `SqliteTradeRepo.add(...)` 写入 `confirm_date` 时使用日历
- `ConfirmPendingTrades` 确认时仅取 `pricing_date` 的 NAV；缺失/<=0 则跳过待重试

## NAV 策略 v0.2（严格版）

- 确认用 NAV：
  - 仅使用“定价日 NAV”（`pricing_date = next_trading_day_or_self(trade_date)`）。
  - `ConfirmPendingTrades` 在定价日 NAV 缺失或 `<= 0` 时直接跳过，保留为 pending，后续可重试；不做任何回退。
- 报表/状态视图用 NAV：
  - 仅使用“当日 NAV”（`day = date.today()`）。
  - 当日 NAV 缺失或 `<= 0` 的基金不计入当日市值与权重；在“NAV 缺失”区块列出基金代码。
  - 不做“最近交易日 NAV”回退；报告文案会提示“总市值可能低估”。

说明：
- 该口径最大程度贴合官方净值的时间口径，避免引入灰色估值与难以解释的回退规则；
- 未来若引入“柔性回退视图”，将以新版本（v0.3+）提供独立开关与清晰标注，不影响 v0.2 的严格口径。

## Rebalance Rules v0.2（基础版）

- 阈值来源：
  - 优先使用 `alloc_config.max_deviation`（按资产类别）；
  - 未配置时使用默认 5% 阈值（0.05）。
- 触发条件：
  - 当 `|实际权重 - 目标权重| > 阈值` 时，给出“增持/减持”建议；
  - 否则标注为“观察（hold）”。
- 建议金额算法：
  - `建议金额 = 总市值 × |偏离| × 50%`（渐进式，保守），仅用于提示；
  - 正偏离（超配）→ 减持；负偏离（低配）→ 增持。
- 口径与限制：
  - 权重与总市值与“市值版日报”一致：仅使用当日 NAV、已确认份额、不回退；
  - 不考虑交易成本、最小申赎份额与税费；
  - 不拆分到具体基金层面（只到资产类别）。
- 输出与集成：
  - 可在 CLI `status --show-rebalance` 附加输出“再平衡建议（基础版）”；
  - 日报可选集成：Job 中先构造日报，再追加建议文本一并发送（后续版本考虑）。

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

3) 计算逻辑（设计基线）
   - 输入：`market`, `trade_date`
   - 步骤：
     1. `pricing_date = next_trading_day_or_self(trade_date)`
     2. `confirm_date = next_trading_day(pricing_date, offset=lag(market))`
     3. 确认时读取 `pricing_date` NAV；若缺失/无效则跳过（不做多级回退）

4) NAV 缺失与确认交互
   - 若确认日缺 NAV：标记该笔交易为“待确认NAV”状态，后续补齐 NAV 时再确认；或在日报/监控里提示缺失。

## 迁移路径
- v0.2 已切换为“定价日 + lag”的确认口径，并引入可替换日历实现；仍仅处理周末。
- 未来：引入节假日表与更丰富的策略（多市场并集、基金级覆盖、回退最多 N 个交易日等）。
