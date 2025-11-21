# Roadmap（版本规划 & 大 TODO）

## 产品定位（当前阶段）

- 工具定位：个人基金投资的“影子记账 + 决策辅助系统”，不负责真实交易执行。
- 真实交易平台：目前聚焦国内，优先支持支付宝场景，后续再考虑其它国内平台。
- 同步模式：伪同步——用户在支付宝等平台完成操作后，在本系统中进行录入/确认。
- 报告口径：以官方日度净值为主，不做盘中交易/高频策略。
- 当下不实现任何 AI 决策，仅为未来 AI 留出数据与结构（标签、视图、上下文快照）。

## 面向 AI 的长期布局（当前只做数据准备）

- 为每个动作打上“意图标签”：
  - 区分：定投执行 / 主动买入 / 再平衡 / 止损减仓 / 现金需求卖出 / 分红再投等（作为主标签集，保持精简稳定）。
  - 记录是谁决定的：`human` / `Dca`/等等 （未来可能有 `AI_ASSISTED`）。 
- 为每个动作保留“当时的上下文快照”：
  - 当时组合的资产分布、风险指标（仓位、集中度、近段收益等）。
  - 当时基金自身状态（近几日涨跌、估值分位）和账户现金情况。
- 区分“计划层 vs 执行层”：
  - 计划：定投计划、目标资产配置、再平衡规则。
  - 执行：实际发生的买卖及与计划的偏离（跳过、提前、延后、超额/不足）。
- 设计面向分析的几张逻辑视图，而不是直接暴露底层表：
  - `UserActionLog`：一行代表“一次投资动作”，带动作标签和关键上下文。
  - `ContextSnapshot`：压缩后的全局组合状态视图，用于复现当时环境。
  - `Outcome`：事后结果标注（例如 T+30/T+90 相对于“什么都不做”的收益差异）。
- 当前阶段只做上述“结构与字段的预留/建模”，不做任何模型训练或自动决策。

## 给未来 AI 的数据设计原则

- **原始信号可重建**：任何衍生字段（收益率、风险分数等）都能从原始交易 / NAV / 持仓重算，避免黑盒。
- **时点一致性**：所有快照和标签都以“当时可见信息”为准，不用事后数据回填，防止决策穿越。
- **主标签 + 扩展标签**：
  - 固定字段：`action_type`、`who_decided`、`plan_id` 等作为核心 schema。
  - 扩展标签：预留 `tags`（JSON）用于后续补充维度，如 `"reason": "stop_loss"`、`"emotion": "fear"`。
- **文本备注友好**：每次动作允许记录简短备注，未来可以用 AI 从自然语言中提取情绪/动机/信息来源等。

## 版本规划总览（当前状态）

- ✅ **v0.1（MVP）**：基础功能完成（交易录入、定投、NAV 抓取、T+N 确认、日报）
- ✅ **v0.2（支付宝闭环）**：核心功能完成（严格 NAV 策略、确认延迟追踪、再平衡建议、区间抓取）
- ✅ **v0.3（日历策略化）**：核心架构完成（交易日历、SettlementPolicy、接口统一、Schema v3）
- 🔄 **v0.4+（待规划）**：周报/月报、历史导入、用户动作日志等增强功能
- 🔮 **v1.x+（远期）**：AI 辅助决策、多市场/多币种
---

## v0.1（当前 MVP，已完成）

**当前可用功能**：
- `CreateTrade`：手动录入买卖交易
- `RunDailyDca` / `SkipDca`：定投计划执行与跳过
- `FetchNavs`：抓取官方净值（支持单日与区间）
- `ConfirmTrades`：T+N 自动确认（A 股 T+1、QDII T+2）
- `MakeDailyReport`：生成日报并推送（Discord）
- `MakeRebalance`：计算再平衡建议
- `MakeStatusSummary`：生成持仓状态（市值/份额视图）

> 命令见 `operations-log.md`；规则见 `settlement-rules.md`。

---

## v0.2（已完成：可信 & 可用的支付宝闭环）

> 目标：让一个只用支付宝的用户，真的可以用这套系统跑完一整套伪同步闭环，而且数字大体可信。

**核心功能已完成**：

- [x] 交易确认规则 v0.2（TradingCalendar + 定价日）
  - 引入 `TradingCalendar` 与"定价日+lag"口径，统一 ConfirmPendingTrades 规则。
- [x] NAV 策略 v0.2（严格版）
  - 确认用定价日 NAV，日报/status 仅用当日 NAV，不做回退并提示低估风险。

  > NAV 策略详细规则见 `docs/settlement-rules.md`。

- [x] 再平衡建议（文字提示 + 建议金额）
  - UseCase `GenerateRebalanceSuggestion` 已落地，CLI `status --show-rebalance` 可查看建议。

  > 再平衡触发条件与计算规则见 `docs/settlement-rules.md`。

- [x] 确认延迟追踪（v0.2.1）
  - 显式标记超期但 NAV 缺失的交易为 `delayed`，在日报中展示延迟原因和建议。
  - 支持自动恢复：补充 NAV 后自动确认并清除延迟标记。

  > 确认延迟处理规则见 `docs/settlement-rules.md`。

- [x] 日报展示日策略 v0.2（严格）
  - 日报/状态默认展示日改为"上一交易日 as_of"。
  - 仅使用展示日 NAV；缺失或 `<=0` 的基金不计入市值与权重，并在文末提示"总市值可能低估"。
  - CLI/Job 提供 `--as-of` 参数覆盖展示日；保持"严格不回退"。

  > 展示日策略与 NAV 严格口径见 `docs/settlement-rules.md`。

- [x] 状态视图开关（兜底）
  - CLI `status` 增加 `--mode {market,shares}`，默认 `market`。
  - 当展示日 NAV 覆盖不足时，使用 `shares` 视图快速查看配置偏离（不依赖 NAV）。

- [x] 历史 NAV 区间抓取（补数闭环）
  - 新增 Job：`fetch_navs_range --from YYYY-MM-DD --to YYYY-MM-DD`。
  - 与确认任务配合：回填完成后执行 `confirm_trades --day <to>` 补确认。

- [x] T+N & NAV 地基收尾（v0.3 已完成）
  - `trading_calendar` 表已建立，支持 DB 日历与严格模式
  - `sync_calendar` / `patch_calendar` Jobs 完成（exchange_calendars + Akshare）
  - `pricing_date` 字段持久化到 `trades` 表（Schema v3）
  - `SettlementPolicy` 引入（卫兵/定价/计数日历组合）

**v0.2 遗留待实现**（优先级低，推迟到后续版本）：
- [ ] 支付宝伪同步闭环（建议 → 执行 → 确认）
- [ ] 交易意图标签（为 AI 准备）
- [ ] Platform & Account 抽象
- [ ] 冷却期机制

---

## v0.3（当前进行中：日历策略化与接口重构）

> 重点：完善交易日历基础设施，实现 QDII 复杂确认规则，统一核心接口。

**已完成**：
- [x] 日历基础设施（v0.3）
  - `CalendarProtocol` 统一接口：`is_open` / `next_open` / `shift`
  - `DbCalendarService`：SQLite 实现，严格模式（缺失即报错）
  - `sync_calendar` Job：从 exchange_calendars 注油基础日历
  - `patch_calendar` Job：从 Akshare 在线修补节假日数据

- [x] SettlementPolicy 策略化（v0.3）
  - 三层日历组合：`guard_calendar` / `pricing_calendar` / `count_calendar`
  - 支持 QDII 场景：CN_A 卫兵 + US_NYSE 定价/计数
  - `pricing_date` 持久化到 `trades` 表（Schema v3）

- [x] 核心接口统一（v0.3）
  - 所有 Protocol 集中到 `src/core/protocols.py`
  - 领域数据类迁移到 `src/core/`（如 `FundInfo`）
  - 删除 `src/usecases/ports.py`（接口层不再在 usecases）
  - Service 命名统一：`NavProtocol` / `NavSourceProtocol` / `ReportProtocol`

**v0.3 遗留待实现**（推迟到 v0.4+）：
- [ ] 周报 / 月报
- [ ] 历史导入（CSV 模板）
- [ ] 盘中估值（附加信息）
- [ ] 用户动作日志 & ContextSnapshot
- [ ] 操作结果 Outcome 标注

---

## AI 阶段（v1.x 以后，暂不实现）

- [ ] 自然语言 AI 接口（基于现有 UseCases）
  - 如：“帮我看下这个月定投执行情况”、“现在要不要减一点仓？” 等查询/建议。
  - 通过工具调用现有 usecases / 逻辑视图，而不是直接访问底层表。

- [ ] AI 辅助定投/再平衡建议
  - 在现有规则基础上，引入个性化偏好与历史行为分析，给出更贴合用户风格的建议。
  - 支持 AI 参与写入 `tags` / `Outcome` 衍生标签，作为“辅助标注”，而非直接覆盖原始数据。

- [ ] 复杂多市场/多币种支持
  - 增加货币、汇率、境外市场与税务相关字段，并统一在 AI 数据视图中处理。
  - 扩展 Platform/Account 层处理不同市场的交易时间、结算规则和税务差异。

---

## 技术债 / 重构

- [ ] 评估在 `adapters/db/sqlite` 层替换手写 SQL
  - 保持 `core` / `usecases` 只依赖领域模型，不直接依赖 ORM。
  - 方案备选：在适配层引入 SQLAlchemy Core 或轻量 Query Builder。
  - 目标：减少硬编码 SQL 和重复 `_row_to_xxx`，提升可维护性与类型安全。

- [ ] **[重要] 修复 T+1/T+2 确认规则的不确定性（v0.2 完成基础版后继续增强）**
  - **当前进展（v0.2）**：已引入 `TradingCalendar` 协议与“定价日+lag”规则，支持按市场区分 T+1/T+2，并处理周末顺延。
  - **问题**：仍未覆盖全部法定节假日与复杂交易日历，无法处理真实业务全部情况。
  - **影响**：边界场景下交易确认可能不准确，影响持仓计算和日报生成。
  - **改进方向**：
    - 引入更完整的交易日历表/数据源，支持节假日规则。
    - 实现动态确认策略，考虑基金特性、交易时间。
    - 添加确认重试机制，处理净值数据缺失。
    - 完善基金模型，支持不同基金类型的确认规则。

- [ ] **[重要] 日报计算精度问题（市值版局限）**
  - **当前进展（v0.2）**：已统一“严格 NAV 口径”：确认用定价日 NAV，日报/status 仅用当日 NAV，缺失时明确提示低估风险。
  - **问题**：市值依赖当日 NAV，当前仍仅使用本地当日 NAV；若缺失或 NAV<=0 会被跳过，导致总市值低估；未覆盖历史/实时 NAV。
  - **影响**：配置偏离和再平衡建议在 NAV 缺失时不准确；跨日滚动或补录 NAV 后需要重算。
  - **改进方向**：
    - 支持多日 NAV 回填与重算，提供最近可用 NAV 或前一交易日回退策略。
    - 引入外部 NAV 数据源/缓存，提升覆盖率与性能。
    - 保留份额视图作为兜底对照，允许在 NAV 缺失时自动切换或同时输出。

---

> 具体命令示例与参数说明见 `docs/operations-log.md`。
> 业务规则（NAV 策略、确认规则、再平衡触发条件等）见 `docs/settlement-rules.md`。
