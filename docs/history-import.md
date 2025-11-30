# 历史账单导入设计

> **状态**：v0.4.2 规划中，骨架已完成，逻辑待实现

## 概述

支持从支付宝等平台导入历史基金交易记录，自动补充净值和份额，写入 `trades` 表并记录 `action_log`。

## 设计边界

| 项目 | 决策 |
|------|------|
| 平台范围 | 只管支付宝，其他平台转换为统一 CSV 模板后导入 |
| 输入方式 | 用户手工/脚本将支付宝原始导出清洗成统一 CSV |
| 净值来源 | 自动调用 `EastmoneyNavService` 抓取历史净值 |
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
| `交易成功` | `confirmed` |
| `付款成功，份额确认中` | `pending`（等待 NAV） |
| `交易关闭` | 跳过 |

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
| trade_id | 新创建的交易 ID |
| intent | `planned`（默认，历史行为无法判断） |
| note | `导入自支付宝账单（{文件名}）` |
| acted_at | CSV 中的交易创建时间 |

---

## Schema 扩展规划（v0.4.2）

### funds 表

```sql
-- 新增 alias 字段
ALTER TABLE funds ADD COLUMN alias TEXT;
```

### trades 表（可选，按需）

```sql
-- 新增 source 字段（标识交易来源）
ALTER TABLE trades ADD COLUMN source TEXT DEFAULT 'manual';
-- 可选值: manual / alipay / ttjj / dca

-- 新增 external_id 字段（外部流水号，用于去重）
ALTER TABLE trades ADD COLUMN external_id TEXT;
-- 唯一约束: (source, external_id)
```

### 导入批次表（远期，按需）

```sql
-- 记录每次导入的元数据
CREATE TABLE import_batches (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    file_name TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    total INTEGER NOT NULL,
    succeeded INTEGER NOT NULL,
    failed INTEGER NOT NULL,
    note TEXT
);
```

---

## 待实现清单

- [ ] `funds.alias` 字段实现
- [ ] `FundRepo.find_by_alias()` 方法
- [ ] CSV 解析器（GBK 编码 + 基金交易过滤）
- [ ] 历史 NAV 批量抓取
- [ ] 份额计算逻辑
- [ ] 导入事务（批量写入 + 回滚）
- [ ] CLI 参数解析
- [ ] 进度条显示

---

## 参考

- 支付宝账单导出：支付宝 App → 我的 → 账单 → 右上角导出
- 东方财富 NAV API：`EastmoneyNavService.get_nav(fund_code, date)`
- 现有确认流程：`src/flows/confirm.py`
