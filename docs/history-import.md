
# 历史账单导入

> v0.4.2 完成。快速参考，详细说明见 `operations-log.md`。

## 概述

支持从支付宝导入历史交易，自动补充净值和份额，写入 `trades` 表和 `action_log`。

## 支付宝账单格式

| 项 | 值 |
|---|---|
| 编码 | GBK |
| 头部行数 | 5（跳过）|
| 分隔符 | 逗号 |
| 基金识别 | 交易对方="蚂蚁财富-蚂蚁（杭州）基金销售有限公司" |
| 基金名称提取 | 商品名称格式："蚂蚁财富-{基金名称}-{买入/卖出}" |

## 快速开始

```bash
# 干跑（检查）
uv run python -m src.cli.history_import --csv data/alipay.csv --mode dry-run

# 实际导入
uv run python -m src.cli.history_import --csv data/alipay.csv --mode apply
```

**输出**：Batch ID（用于后续回填）

## 关键设计

**基金名称映射**：使用 `funds.alias` 字段，需先配置：
```bash
uv run python -m src.cli.fund add --code 016057 --alias "嘉实纳斯达克100ETF联接(QDII)A"
```

**NAV 处理**：自动抓取，缺失时降级为 pending，后续可手动确认。

**幂等性**：基于 `external_id` 去重，重复导入不会重复插入。

## 导入后的 DCA 事实查看与回填（v0.4.5+）

```
导入交易（strategy="none"）
    ↓
查看事实快照：dca_facts batch <batch_id> / dca_facts fund <batch_id> <code>
    ↓
根据事实人工决定计划：dca_plan add --fund <code> --amount ... --freq ... --rule ...
    ↓
回填归属：dca_plan backfill --batch-id <batch_id> --mode apply
```

**关键**：
- 事实快照由 `dca_facts` 提供（金额/间隔分布、候选片段、异常概览），不再依赖 `dca_plan infer` 草案。
- 回填仍以日期为准决定归属，金额仅记录偏差。详见 operations-log.md。

## Schema 变更（v0.4.2-v0.4.3）

```sql
-- funds 表：基金名称映射
ALTER TABLE funds ADD COLUMN alias TEXT;

-- trades 表：导入追溯 + DCA 归属
ALTER TABLE trades ADD COLUMN external_id TEXT UNIQUE;
ALTER TABLE trades ADD COLUMN import_batch_id INTEGER;
ALTER TABLE trades ADD COLUMN dca_plan_key TEXT;

-- 导入批次表
CREATE TABLE import_batches (
    id INTEGER PRIMARY KEY,
    source TEXT,
    created_at TEXT,
    note TEXT
);
```
