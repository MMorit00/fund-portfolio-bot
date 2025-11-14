# Operations Log（环境/工具/运维）

## 2025-11-14 初始化

- 创建基础目录结构：`src/core`, `src/usecases`, `src/adapters`, `src/app`, `src/jobs`, `docs`, `scripts`, `data`
- 约定：敏感信息走环境变量（`.env` 不入库）；CI 使用 Secrets；配置入口 `src/app/config.py`
- SQL 打印策略：SQLite `set_trace_callback`（受 `ENABLE_SQL_DEBUG` 控制）
- 备份策略：`scripts/backup_db.sh` 手动快照（重大变更前执行）

