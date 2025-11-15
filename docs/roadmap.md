# Roadmap（版本规划 & 大 TODO）

## v0.1（当前 MVP）
- [x] 基金 & 资产类别管理（FundRepo / AllocConfig）
- [x] 交易记录：`/buy` `/sell`（CreateTrade）—— CLI 已完成
- [x] 定投计划：生成 pending 与跳过（RunDailyDca / SkipDcaForDate）—— RunDailyDca 已完成并装配
- [x] 官方净值抓取（NavProvider + NavRepo）—— 本地 NavProvider 已完成（方案 A）
- [x] T+1/T+2 确认（ConfirmPendingTrades）—— 已完成并装配
- [x] 日报（GenerateDailyReport + Discord Webhook）—— 轻量版（基于份额）已完成，后续升级市值精度

### 当前功能一览表（v0.1）

- 基金与资产配置管理：管理基金基础信息与目标资产配置；状态：已完成；主要实现：`src/adapters/db/sqlite/fund_repo.py`、`src/adapters/db/sqlite/alloc_config_repo.py`。
- 交易录入 CLI：通过命令行录入买入/卖出交易；状态：已完成；入口：`src/app/main.py` 中 `buy` / `sell` 子命令。
- 定投计划执行：根据定投计划生成当日 pending 交易；状态：已完成；主要实现：`src/usecases/dca/run_daily.py`、`src/jobs/run_dca.py`。
- 定投跳过：人工指定基金在某日的定投 pending 交易标记为 skipped；状态：已完成；入口：CLI `skip-dca`（`src/app/main.py`），实现：`src/usecases/dca/skip_date.py`、`src/adapters/db/sqlite/trade_repo.py`。
- 本地净值提供（方案 A）：从本地 NAV 表读取净值，不做 HTTP 抓取；状态：已完成；主要实现：`src/app/wiring.py` 中 `LocalNavProvider`，`src/adapters/db/sqlite/nav_repo.py`。
- 交易确认（T+N）：按确认日规则将 pending 交易转为已确认；状态：已完成；主要实现：`src/usecases/trading/confirm_pending.py`、`src/jobs/confirm_trades.py`。
- 日报生成（份额版）：基于份额计算资产配置并生成文本日报；状态：已完成（轻量版，市值精度待改进）；主要实现：`src/usecases/portfolio/daily_report.py`、`src/jobs/daily_report.py`。
- Discord 推送占位实现：通过 Discord Webhook 发送文本（当前为占位/打印）；状态：已完成占位实现；主要实现：`src/adapters/notify/discord_report.py`。
- SQLite 初始化与种子脚本：管理 schema 初始化，提供备份与种子数据脚本；状态：已完成；主要实现：`src/adapters/db/sqlite/db_helper.py`、`scripts/dev_seed_db.py`、`scripts/backup_db.sh`。

## v0.2（计划）
- [ ] 周报 / 月报（基础版）
- [ ] 再平衡建议（文字提示 + 建议区间）
- [ ] 冷却期机制配置化

## v0.3（未来方向）
- [ ] 历史导入（严格 CSV 模板）
- [ ] 盘中估值作为附加信息（不作为核心口径）
- [ ] 自然语言 AI 接口（基于现有 UseCases）




## 技术债 / 重构

- [ ] 评估在 `adapters/db/sqlite` 层替换手写 SQL
  - 保持 `core` / `usecases` 只依赖领域模型，不直接依赖 ORM
  - 方案备选：在适配层引入 SQLAlchemy Core 或 轻量 Query Builder
  - 目标：减少硬编码 SQL 和重复 `_row_to_xxx`，提升可维护性与类型安全

- [ ] **[重要] 修复 T+1/T+2 确认规则的不确定性**
  - **问题**：当前 `get_confirm_date()` 过于简化，无法处理真实业务复杂情况
  - **影响**：交易确认可能不准确，影响持仓计算和日报生成
  - **改进方向**：
    - 引入交易日历表，支持节假日规则
    - 实现动态确认策略，考虑基金特性、交易时间
    - 添加确认重试机制，处理净值数据缺失
    - 完善基金模型，支持不同基金类型的确认规则

- [ ] **[重要] 日报计算精度问题**
  - **问题**：当前 `GenerateDailyReport` 基于份额计算权重，不是基于市值
  - **影响**：配置偏离分析不准确，再平衡建议可能错误
  - **改进方向**：
    - 集成实时净值数据进行市值计算
    - 缓存市值计算结果提升性能
    - 提供份额视图和市值视图两种模式
