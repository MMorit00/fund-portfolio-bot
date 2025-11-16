# Coding Log（功能/架构决策）

## 2025-11-14 项目骨架

### 完成内容
- 生成文档骨架与目录结构（core/usecases/adapters/app/jobs）
- 确认命名与分层约定：路径表达领域，文件名简短；依赖通过 Protocol 注入
- 放弃：AI/NLU、历史导入、盘中估值（均不在 MVP 范围）

### 决策
- 使用每日官方净值作为唯一口径；报告/再平衡基于日级数据
- 错误处理：核心抛异常；入口捕获并打印
- 日志：MVP 不引 logging；使用 `app/log.py` 封装 `print`


## 2025-11-15 SQLite Schema v0.1

### 完成内容
- 梳理 v0.1 需要的表（funds/trades/navs/dca_plans/alloc_config/meta），统一 Decimal → TEXT 持久化。
- trades 表新增 confirm_date 字段，创建时直接写入 `get_confirm_date` 的结果，方便 SQL 过滤。
- 新建 `docs/sql-schema-v0.1.md` 记录表结构，作为 DB helper 的权威来源。

### 决策
- schema_version 写入 meta 表，便于未来迁移；当前仅记录 `schema_version=1`。
- Decimal 值全部以字符串写入，读取时再转 Decimal，避免浮点误差。

## 2025-11-15 SQLite Helper & 仓储实现

### 完成内容
- 编写 `SqliteDbHelper`，集中管理连接、trace、schema 初始化，首版 schema_version=1。
- 实现 `SqliteTradeRepo/NavRepo/FundRepo/DcaPlanRepo/AllocConfigRepo`，全部按 Protocol 定义落地。
- 新增 `scripts/dev_seed_db.py`，通过设置 `DB_PATH` 可快速初始化/自测仓储行为。

### 决策
- 交易表确认日持久化，`list_pending_to_confirm` 纯 SQL 过滤，避免 Python 额外遍历。
- `position_shares` 逻辑在 Python 侧聚合，保证 Decimal 精度，不依赖 SQLite 浮点聚合。

- 决策：短期（v0.1）继续使用 sqlite3 + 手写 SQL；后续在 adapters 层集中评估引入 SQLAlchemy Core/Query Builder 的可行性。

## 2025-11-15 依赖装配 & Job 入口完成

### 完成内容
- 实现 `app/wiring.py` 的 `DependencyContainer` 上下文管理器，统一管理 DB 连接、仓储、适配器、UseCase 的生命周期。
- 实现 `LocalNavProvider`（方案 A）：从 NavRepo 读取本地 NAV，不做 HTTP 抓取，满足 v0.1 基于 seed/手工数据的需求。
- 完成 3 个 Job 装配：
  - `jobs/run_dca.py`：调用 `RunDailyDca`，生成当日定投交易
  - `jobs/confirm_trades.py`：调用 `ConfirmPendingTrades`，确认到期交易份额
  - `jobs/daily_report.py`：调用 `GenerateDailyReport`，生成并推送日报
- 使用 `dev_seed_db.py` 验证完整流程：创建交易 → 模拟确认 → 查看结果（1000 ÷ 1.5 = 666.67 份）✅

### 决策
- NAV 策略采用方案 A（本地读取）：LocalNavProvider 仅从 NavRepo 读取，不做实时抓取，适合 MVP 阶段快速验证。
- 所有 Job 统一使用 `with DependencyContainer() as container:` 模式，确保 DB 连接正确关闭。
- Job 日志格式：开始/结束标记 + emoji 状态（✅/⚠️/❌），便于 cron/Actions 输出查看。

### 代码规范优化
- 修正 `LocalNavProvider.get_nav()` 类型注解：参数 `day: date`，返回值 `Optional[Decimal]`，移除所有 `# type: ignore`。
- 移除不必要的向后兼容代码，保持 wiring 层简洁单一。

## 2025-11-15 交易 CLI（buy/sell）

### 完成内容
- 实现 `app/main.py` CLI 入口，支持 buy/sell 子命令：
  - 参数：`--fund-code`（必需）、`--amount`（必需）、`--date`（可选，ISO 格式 YYYY-MM-DD，默认今天）
  - 参数验证：金额必须为正 Decimal，日期必须为 ISO 格式
  - 错误处理：友好的中文提示 + 退出码（4=参数/业务错误，5=未知错误）
  - 成功输出：完整摘要（ID、fund、type、amount、date、confirm_date）
- 接入 `DependencyContainer` 和 `CreateTrade` UseCase，完成端到端的交易录入流程。

### 决策
- CLI 风格采用简洁设计：`python -m src.app.main buy --fund-code 110022 --amount 1000`。
- 日期参数固定 ISO 格式（YYYY-MM-DD），不支持相对日期（yesterday/-1d），保持简单。
- 错误输出包含详细提示：如基金代码不存在时提示运行 dev_seed_db。
- 成功输出包含 confirm_date，方便用户预期交易确认时间。

## 2025-11-15 代码组织规范化
### 决策
- 确立代码组织原则："入口在上，工具在下；公开在上，私有在下"。
  - 类中：`__init__` → 公开方法 → 私有方法
  - 模块中：公开类/函数 → 模块私有工具函数
- 将此原则写入 `CLAUDE.md`，作为项目编码规范的一部分。
- 验证修改后所有 Job 和 CLI 均正常运行。

## 2025-11-16 SkipDcaForDate CLI

### 完成内容
- 在 `TradeRepo` 补充 `skip_dca_for_date(fund_code, day)`，SQLite 实现按 fund_code + trade_date + type='buy' + status='pending' 更新为 `skipped`，返回影响行数。
- 在 UseCase `SkipDcaForDate` 中调用仓储，不再是占位。
- `DependencyContainer` 暴露 `get_skip_dca_usecase()`，供入口调用。
- CLI 增加 `skip-dca` 子命令：`python -m src.app.main skip-dca --fund-code 110022 --date 2025-11-15`（date 默认今天），输出影响的 pending 数量。

### 决策
- v0.1 仅更新状态为 `skipped`，不记录原因/操作人；未来需要原因时可复用 trades.remark。
- 跳过范围明确：仅当日 pending 买入；不影响卖出、其他日期或已确认记录。

## 2025-11-17 日报市值版 & 状态 CLI

### 完成内容
- 日报升级为市值视图优先：在 `GenerateDailyReport` 中集成 `NavProvider`，市值=份额×NAV，缺失 NAV 的基金会被跳过并提示；保留份额模式兼容。
- `daily_report` Job 默认发送市值版（mode="market"）。
- 新增终端 `status` 子命令：`python -m src.app.main status`，直接输出当前市值视图。
- 添加确认规则设计草稿文档：`docs/settlement-rules.md`，记录现状与未来交易日历/确认策略规划。

### 决策
- NAV 来源继续使用本地 NavRepo（方案 A），缺失 NAV 时不估算，提示缺失列表。
- 确认规则后续演进：引入交易日历表与 per-market 配置，当前保持周末顺延的 T+1/T+2 简化逻辑。

## 2025-11-17 确认份额口径修订

### 完成内容
- `ConfirmPendingTrades` 调整为：首选“交易日 NAV”计算份额；若缺失或<=0，回退到“确认日 NAV”；均无效则跳过。
- 同步文档：`docs/sql-schema-v0.1.md` 将 `trades.nav` 描述改为“用于确认的净值（首选交易日 NAV；可回退确认日）”。

### 原因
- 公募申购定价以交易日净值为准；之前实现按确认日 NAV 会与数据写口径/业务口径不一致。

## 2025-11-18 交易确认规则 v0.2（TradingCalendar + 定价日）

### 完成内容
- 引入 `TradingCalendar` 协议与 `SimpleTradingCalendar`（仅周末非交易日）。
- 重写 `get_confirm_date(market, trade_date, calendar)`：确认日=定价日+lag（A=1，QDII=2）。
- `SqliteTradeRepo.add(...)` 写 confirm_date 时使用日历；
- `ConfirmPendingTrades` 取 NAV：仅使用定价日（`<=0` 视为缺失，不回退确认日）。
- CLI 计算展示的 confirm_date 改为基于 v0.2 规则。
- 文档同步：`docs/settlement-rules.md`、新增 `docs/sql-migrations-v0.2.md` 草案。

### 决策
- v0.2 范围仅支持 `A` 与 `QDII`，不做基金级 lag；不引入节假日表，仅处理周末。
- 继续在创建交易时预写 `confirm_date`，历史记录不回溯更改。

## 2025-11-19 NAV 策略 v0.2（严格版）

### 完成内容
- 统一 NAV 使用口径：
  - 确认用例：仅使用“定价日 NAV”，缺失/<=0 直接跳过待重试（不做回退）。
  - 日报/状态视图：仅使用“当日 NAV”，缺失/<=0 的基金不计入市值与权重并列入缺失列表。
- 日报数据结构扩展：
  - `ReportData` 新增统计字段 `total_funds_in_position`、`funds_with_nav`（仅市值模式有意义）。
  - 渲染在缺失 NAV 时输出提示：`今日 X/Y 只基金有有效 NAV，总市值可能低估`。
- 文档：在 `docs/settlement-rules.md` 增加“小节：NAV 策略 v0.2（严格版）”。

### 决策
- v0.2 不做“最近交易日 NAV”回退，避免灰色估值；当日缺失 NAV 的基金完全排除并提示可能低估。
- 外部数据源适配器与抓取 Job 保持占位状态，等待后续接入时再落地重试/缓存策略。
