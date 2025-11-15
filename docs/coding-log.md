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
