# Roadmap（版本规划 & 大 TODO）

## v0.1（当前 MVP）
- [x] 基金 & 资产类别管理（FundRepo / AllocConfig）
- [x] 交易记录：`/buy` `/sell`（CreateTrade）—— CLI 已完成
- [x] 定投计划：生成 pending 与跳过（RunDailyDca / SkipDcaForDate）—— RunDailyDca 已完成并装配
- [x] 官方净值抓取（NavProvider + NavRepo）—— 本地 NavProvider 已完成（方案 A）
- [x] T+1/T+2 确认（ConfirmPendingTrades）—— 已完成并装配
- [x] 日报（GenerateDailyReport + Discord Webhook）—— 市值版（本地 NAV，缺失跳过并标注）已完成，保留份额模式用于兼容

### 当前功能一览表（v0.1）

- 录入交易（买/卖）  
  - UseCase：`CreateTrade`  
  - 入口：CLI `buy` / `sell`
- 定投计划执行（按计划生成当日 pending）  
  - UseCase：`RunDailyDca`  
  - 入口：Job `run_dca`
- 定投跳过（指定基金 + 日期）  
  - UseCase：`SkipDcaForDate`  
  - 入口：CLI `skip-dca`
- 交易确认（T+N 转已确认）  
  - UseCase：`ConfirmPendingTrades`  
  - 入口：Job `confirm_trades`
- 日报生成（市值/份额视图）  
  - UseCase：`GenerateDailyReport`  
  - 入口：Job `daily_report`
- 状态查看（终端输出市值视图）  
  - UseCase：`GenerateDailyReport`  
  - 入口：CLI `status`
- 再平衡建议（基础版，CLI 扩展）  
  - UseCase：`GenerateRebalanceSuggestion`  
  - 入口：CLI `status --show-rebalance`

## v0.2（进行中）
- [ ] 周报 / 月报（基础版）
- [x] 交易确认规则 v0.2（TradingCalendar + 定价日）—— 引入 `TradingCalendar` 与“定价日+lag”口径，统一 ConfirmPendingTrades 规则
- [x] NAV 策略 v0.2（严格版）—— 确认用定价日 NAV，日报/status 仅用当日 NAV，不做回退并提示低估风险
- [x] 再平衡建议（文字提示 + 建议金额）—— UseCase `GenerateRebalanceSuggestion` 已落地，CLI `status --show-rebalance` 可查看建议
- [ ] 冷却期机制配置化

## v0.3（未来方向）
- [ ] 历史导入（严格 CSV 模板）
- [ ] 盘中估值作为附加信息（不作为核心口径）
- [ ] 自然语言 AI 接口（基于现有 UseCases）
- [ ] 静态类型与代码检查（mypy/ruff）最小配置与渐进收紧（文档先行→最小配置→逐步收紧）




## 技术债 / 重构

- [ ] 评估在 `adapters/db/sqlite` 层替换手写 SQL
  - 保持 `core` / `usecases` 只依赖领域模型，不直接依赖 ORM
  - 方案备选：在适配层引入 SQLAlchemy Core 或 轻量 Query Builder
  - 目标：减少硬编码 SQL 和重复 `_row_to_xxx`，提升可维护性与类型安全

- [ ] **[重要] 修复 T+1/T+2 确认规则的不确定性**
  - **当前进展（v0.2）**：已引入 `TradingCalendar` 协议与“定价日+lag”规则，支持按市场区分 T+1/T+2，并处理周末顺延。
  - **问题**：仍未覆盖法定节假日与复杂交易日历，无法处理真实业务全部情况
  - **影响**：交易确认可能不准确，影响持仓计算和日报生成
  - **改进方向**：
    - 引入交易日历表，支持节假日规则
    - 实现动态确认策略，考虑基金特性、交易时间
    - 添加确认重试机制，处理净值数据缺失
    - 完善基金模型，支持不同基金类型的确认规则

- [ ] **[重要] 日报计算精度问题（市值版局限）**
  - **当前进展（v0.2）**：已统一“严格 NAV 口径”：确认用定价日 NAV，日报/status 仅用当日 NAV，缺失时明确提示低估风险。
  - **问题**：市值依赖当日 NAV，当前仍仅使用本地当日 NAV；若缺失或 NAV<=0 会被跳过，导致总市值低估；未覆盖历史/实时 NAV。
  - **影响**：配置偏离和再平衡建议在 NAV 缺失时不准确；跨日滚动或补录 NAV 后需要重算。
  - **改进方向**：
    - 支持多日 NAV 回填与重算，提供最近可用 NAV 或前一交易日回退策略。
    - 引入外部 NAV 数据源/缓存，提升覆盖率与性能。
    - 保留份额视图作为兜底对照，允许在 NAV 缺失时自动切换或同时输出。

- [ ] 静态检查与类型检查引入计划（规划）
  - 阶段 1：文档指导（已完成，见 docs/python-style.md 类型与注解规范）
  - 阶段 2：生成最小 mypy/ruff 配置文件（不在当前阶段落库，仅准备草案）
  - 阶段 3：启用基础规则并修复增量问题（不影响现有功能迭代）
  - 阶段 4：逐步收紧（如 disallow-any-generics 等），最终可选接入 CI
