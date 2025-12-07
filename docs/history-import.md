
# 历史账单导入设计

> **状态**：v0.4.2 ✅ 主流程已完成（CSV 解析 → 映射 → NAV 抓取 → 份额计算 → 写入），待优化：进度条、错误恢复策略

## 概述

支持从支付宝等平台导入历史基金交易记录，自动补充净值和份额，写入 `trades` 表并记录 `action_log`。

## 设计边界

| 项目 | 决策 |
|------|------|
| 平台范围 | 只管支付宝，其他平台转换为统一 CSV 模板后导入 |
| 输入方式 | 用户手工/脚本将支付宝原始导出清洗成统一 CSV |
| 净值来源 | 自动调用 `FundDataClient` 抓取历史净值 |
| 份额计算 | `shares = amount / nav` |
| ActionLog | 每笔交易补一条行为日志 |
| 幂等策略 | 开发阶段可删库重建，生产阶段用 `external_id` 去重 |

---

## 支付宝账单格式

### 文件特征

| 项目 | 值 |
|------|------|
| 编码 | GBK |
| 头部行数 | 5 行（跳过） |
| 列数 | 16 列 |
| 分隔符 | 逗号 |

### 列定义

```
交易号, 商家订单号, 交易创建时间, 付款时间, 最近修改时间, 交易来源地,
类型, 交易对方, 商品名称, 金额（元）, 收/支, 交易状态, 服务费（元）,
成功退款（元）, 备注, 资金状态
```

### 基金交易识别特征

```
交易对方 = "蚂蚁财富-蚂蚁（杭州）基金销售有限公司"
资金状态 = "资金转移"
商品名称格式 = "蚂蚁财富-{基金名称}-{买入/卖出}"
```

### 字段可用性

| 支付宝字段 | 可用性 | 用途 |
|------------|--------|------|
| 交易号 | ✅ 有 | `external_id`（去重） |
| 交易创建时间 | ✅ 有 | `trade_date` + `acted_at` |
| 金额（元） | ✅ 有 | `amount` |
| 商品名称 | ⚠️ 需解析 | 提取基金名称 + 交易类型 |
| 交易状态 | ✅ 有 | 判断是否已确认 |
| 基金代码 | ❌ 没有 | 需通过 `alias` 映射 |
| 份额 | ❌ 没有 | 需通过 NAV 计算 |
| 净值 | ❌ 没有 | 需调用东方财富 API |

---

## 基金名称映射（alias 字段）

### Schema 变更（v0.4.2 规划）

```sql
-- funds 表新增 alias 字段
ALTER TABLE funds ADD COLUMN alias TEXT;
```

### 映射示例

| fund_code | name | alias |
|-----------|------|-------|
| 016057 | 嘉实纳指A | 嘉实纳斯达克100ETF联接(QDII)A |
| 001551 | 天弘纳指C | 天弘纳斯达克100指数(QDII)C |
| 161130 | 易方达纳指A | 易方达纳斯达克100ETF联接(QDII-LOF)A |
| 007380 | 大成纳指C | 大成纳斯达克100ETF联接(QDII)C |
| 270042 | 广发纳指A | 广发纳斯达克100ETF联接(QDII)A |

### 映射逻辑

```python
def find_fund_by_alias(alias: str) -> str | None:
    """从 funds 表查找匹配 alias 的 fund_code"""
    # SELECT fund_code FROM funds WHERE alias = ?
```

---

## 导入流程设计

### 数据流

```
┌─────────────────┐
│  支付宝 CSV     │ (GBK 编码)
└────────┬────────┘
         │ 1. 解析 CSV
         ▼
┌─────────────────┐
│  AlipayRecord   │ (基金名称, 日期, 金额, 交易号)
└────────┬────────┘
         │ 2. 名称 → 代码映射 (alias)
         ▼
┌─────────────────┐
│  HistoryImport  │ (fund_code, trade_date, amount)
│  Record         │
└────────┬────────┘
         │ 3. 抓取历史 NAV (eastmoney)
         │ 4. 计算份额 = amount / nav
         ▼
┌─────────────────┐
│  Trade          │ (status=confirmed)
│  ActionLog      │ (action=buy/sell, note=导入)
└─────────────────┘
```

### 导入模式

| 模式 | 说明 |
|------|------|
| `dry_run` | 只解析校验，不写入数据库 |
| `apply` | 实际写入 trades + action_log |

### 状态映射

| 支付宝状态 | 导入状态 |
|------------|----------|
| `交易成功` | `confirmed`（如 NAV 可用）/ `pending`（如 NAV 暂缺） |
| `付款成功，份额确认中` | `pending`（等待 NAV） |
| `交易关闭` | 跳过 |

### NAV 缺失处理策略（v0.4.2+ 优化）

**设计理念**：尽量导入，利用现有确认流程。

| 场景 | 处理方式 | 理由 |
|------|---------|------|
| **confirmed + NAV 可用** | ✅ 写入为 confirmed，份额已计算 | 正常流程 |
| **confirmed + NAV 缺失** | ✅ 自动降级为 pending，后续自动确认 | 支付宝显示"交易成功"说明交易已发生，只是暂时拿不到净值，不应拒绝导入 |
| **pending + NAV 缺失** | ✅ 写入为 pending，等待后续确认 | pending 本身就是"待确认"状态，与日常流程一致 |

**降级机制**：
- 当 `target_status="confirmed"` 但 NAV 抓取失败时，自动修改为 `target_status="pending"`
- 降级后的记录会成功写入 trades 表，等待后续 `confirm_trades` 自动处理
- CLI 输出会显示降级数量："⚠️ 降级为 pending: X 笔（NAV 暂缺，后续自动确认）"

**用户应对策略**（如净值永久缺失）：
1. **等待几天后重试**：NAV 可能延迟发布，过几天重新运行导入（幂等安全）
2. **手动确认**：使用 `trade confirm-manual --id <ID> --shares <份额> --nav <净值>` 手动确认
3. **取消交易**：如不重要可用 `trade cancel --id <ID>` 删除

---

## CLI 用法设计

```bash
# 干跑：检查 CSV 是否有问题
python -m src.cli.history_import --csv data/alipay.csv --mode dry-run

# 实际导入
python -m src.cli.history_import --csv data/alipay.csv --mode apply

# 指定平台（默认 alipay）
python -m src.cli.history_import --csv data/alipay.csv --source alipay

# 禁用 ActionLog 记录
python -m src.cli.history_import --csv data/alipay.csv --mode apply --no-actions
```

### 输出示例

```
📥 历史账单导入（dry-run 模式）

CSV 文件: data/alipay.csv
识别到基金交易: 103 笔

映射结果:
  ✅ 嘉实纳斯达克100ETF联接(QDII)A → 016057
  ✅ 天弘纳斯达克100指数(QDII)C → 001551
  ❌ 某未知基金 → 未找到映射

NAV 抓取: 98/103 成功
份额计算: 98/103 完成

待导入:
  - 买入: 98 笔
  - 跳过: 5 笔（NAV 缺失或映射失败）

使用 --mode apply 执行实际导入
```

---

## ActionLog 补录策略

每笔导入交易补一条 ActionLog：

| 字段 | 值 |
|------|------|
| action | `buy` / `sell`（与交易类型一致） |
| actor | `human` |
| source | `import` |
| trade_id | 新创建的交易 ID |
| intent | `planned`（默认，历史行为无法判断） |
| note | `导入自支付宝账单（{文件名}）` |
| acted_at | CSV 中的交易创建时间 |
| strategy | `none`（初始值，见下节说明） |

---

## 导入账单与 DCA 语义

### 导入与 DCA 语义

**初始状态**：导入交易的 `strategy="none"`，因无法区分手动/定投。

**后续回填**：通过 `dca_plan backfill` 为符合定投规则的交易标记 `strategy="dca"`。

> 详见 `CLAUDE.md`"算法 vs AI 分工"节：导入/回填只负责事实（规则匹配），语义判断交给 AI。

### DCA 语义回填（✅ 已实现，v0.4.3）

**命令**：`dca_plan backfill --batch-id <ID> [--mode apply] [--fund <CODE>]`

**流程**：
1. 推断定投计划（`dca_plan infer`）并创建 DCA 计划
2. 运行回填：`dca_plan backfill --batch-id <ID> --mode dry-run`（检查）或 `--mode apply`（执行）

**匹配规则**（规则层只输出事实，日期+同日唯一性决定归属）：
- **日期轨道**：交易日期是否符合计划频率（daily/weekly/monthly）
- **同日唯一性**：同一天多笔买入时，仅选金额偏差最小的一笔
- **金额事实**：金额偏差作为事实字段记录（`BackfillMatch.amount_deviation`），不参与归属判断

**核心逻辑**：为符合规则的交易更新 `dca_plan_key` 和 `strategy="dca"`

---

## Schema 扩展（v0.4.2）

### funds 表（✅ 已实现）

```sql
-- 新增 alias 字段
ALTER TABLE funds ADD COLUMN alias TEXT;
```

### trades 表（✅ 已实现）

```sql
-- 新增 external_id 字段（外部流水号，用于去重）
ALTER TABLE trades ADD COLUMN external_id TEXT UNIQUE;
```

**注**：`source` 字段已取消（不需要区分来源，`external_id` 足够用于去重）

### 导入批次表（✅ 已实现，v0.4.3）

```sql
-- 记录每次导入的元数据（用于追溯和撤销）
CREATE TABLE import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    note TEXT
);

-- trades 表增加批次关联
ALTER TABLE trades ADD COLUMN import_batch_id INTEGER;  -- FK to import_batches
ALTER TABLE trades ADD COLUMN dca_plan_key TEXT;        -- 定投计划标识
```

**Batch 机制说明（v0.4.3）**：

每次历史导入（`mode='apply'`）会自动创建一个 `import_batch` 记录：
- **`batch_id`**：导入批次的唯一标识
- **作用范围**：
  - 仅历史导入的交易会关联 `import_batch_id`
  - 手动交易（`trade buy/sell`）和自动定投（`dca run`）的 `import_batch_id` 为 NULL
- **使用场景**：
  - 撤销导入：`DELETE FROM trades WHERE import_batch_id = ?`
  - 查询批次：`SELECT * FROM trades WHERE import_batch_id = ?`
  - DCA 回填（Phase 2）：只作用于指定 batch 的数据

**CLI 输出示例**：
```
✅ 导入完成
   总计: 103 笔
   成功: 103 笔
   失败: 0 笔
   跳过: 0 笔
   成功率: 100.0%
   📦 Batch ID: 1
```

---

## 实现状态

✅ v0.4.2 完成：CSV 解析 → 基金映射 → NAV 抓取 → 份额计算 → 去重 → ActionLog 补录
✅ v0.4.3 完成：Import Batch 机制 + DCA 回填工具

---

## 参考

- 支付宝账单导出：支付宝 App → 我的 → 账单 → 右上角导出
- 基金 NAV API：`FundDataClient.get_nav(fund_code, date)`
- 现有确认流程：`src/flows/trade.py:confirm_trades()`
