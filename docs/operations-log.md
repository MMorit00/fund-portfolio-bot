# Operations Log（环境/工具/运维）

## 2025-11-14 初始化

- 创建基础目录结构：`src/core`, `src/usecases`, `src/adapters`, `src/app`, `src/jobs`, `docs`, `scripts`, `data`
- 约定：敏感信息走环境变量（`.env` 不入库）；CI 使用 Secrets；配置入口 `src/app/config.py`
- SQL 打印策略：SQLite `set_trace_callback`（受 `ENABLE_SQL_DEBUG` 控制）
- 备份策略：`scripts/backup_db.sh` 手动快照（重大变更前执行）

## 2025-11-15 手动录入交易（CLI）

### 使用方法

**买入基金**：
```bash
python -m src.app.main buy --fund-code 110022 --amount 1000
python -m src.app.main buy --fund-code 110022 --amount 1000.50 --date 2025-11-15
```

**卖出基金**：
```bash
python -m src.app.main sell --fund-code 000001 --amount 500
python -m src.app.main sell --fund-code 000001 --amount 500.50 --date 2025-11-16
```

### 参数说明
- `--fund-code`（必需）：基金代码，必须已在 funds 表中配置
- `--amount`（必需）：交易金额，支持整数或小数（如 1000 或 1000.50）
- `--date`（可选）：交易日期，格式为 YYYY-MM-DD，默认今天

### 输出示例

**成功**：
```
✅ 交易已创建：ID=2 fund=110022 type=buy amount=1000 date=2025-11-15 confirm_date=2025-11-17
```

**错误（基金不存在）**：
```
❌ 错误：未知基金代码：999999
提示：请检查是否已在 funds 表中配置，或先运行 dev_seed_db
```

**错误（金额格式无效）**：
```
❌ 错误：金额格式无效：abc（期望 Decimal，例如 1000 或 1000.50）
```

