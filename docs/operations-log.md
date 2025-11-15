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


## 2025-11-15 开发自测流程

### v0.1 完整流程验证

以下是本地开发环境的自测步骤，用于验证从交易录入到日报生成的完整闭环：

**步骤 1：初始化数据库**
```bash
# 运行 seed 脚本，创建测试数据
PYTHONPATH=. python scripts/dev_seed_db.py
```

**步骤 2：手动录入交易（可选）**
```bash
# 使用 CLI 录入新交易
python -m src.app.main buy --fund-code 110022 --amount 1000
python -m src.app.main sell --fund-code 000001 --amount 500.50 --date 2025-11-16
```

**步骤 3：模拟定投生成**
```bash
# 运行定投 job（如果今天符合定投规则）
python -m src.jobs.run_dca
```

**步骤 4：确认交易份额**
```bash
# 确认到期的 pending 交易
python -m src.jobs.confirm_trades
```

**步骤 5：生成日报**
```bash
# 生成并查看日报内容
python -m src.jobs.daily_report
```

### 日报输出示例

```
【持仓日报 2025-11-15】
总份额：666.67

资产配置：
- CGB_3_5Y：0.0% (目标 20.0%，低配 -20.0%)
- CSI300：100.0% (目标 50.0%，超配 +50.0%)
- US_QDII：0.0% (目标 30.0%，低配 -30.0%)

⚠️ 再平衡提示：
- CSI300 超配，建议减持
- US_QDII 低配，建议增持
- CGB_3_5Y 低配，建议增持
```

### 注意事项

1. **NAV 数据要求**：
   - 当前版本使用本地 NAV（方案 A）
   - `confirm_trades` 需要对应日期的 NAV 数据才能确认交易
   - 可通过 `dev_seed_db.py` 或手动插入 NAV 数据

2. **日报内容说明**：
   - 当前版本显示"总份额"而非"总市值"
   - 权重计算基于份额归一化，不依赖 NAV
   - 适用于快速查看配置偏离情况

3. **Discord 推送**：
   - 需要配置 `DISCORD_WEBHOOK_URL` 环境变量
   - 未配置时日报仍会生成，但不会推送
