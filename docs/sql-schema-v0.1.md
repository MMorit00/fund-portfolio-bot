# SQLite Schema v0.1

v0.1 关注基金、交易、净值、定投与资产配置，全部持久化在单个 SQLite 数据库中。Decimal 数值统一使用 `TEXT` 存储，写入/读出均通过 `Decimal(str_value)` 处理，避免浮点误差。

## 表结构

### funds
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| fund_code | TEXT PRIMARY KEY | 基金代码 |
| name | TEXT NOT NULL | 基金名称 |
| asset_class | TEXT NOT NULL | 对应 `AssetClass` 枚举值 |
| market | TEXT NOT NULL | 申购市场，`A` 或 `QDII` |

### trades
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INTEGER PRIMARY KEY AUTOINCREMENT |
| fund_code | TEXT NOT NULL |
| type | TEXT NOT NULL | `buy` / `sell` |
| amount | TEXT NOT NULL | 金额（Decimal 序列化） |
| trade_date | TEXT NOT NULL | `YYYY-MM-DD` |
| status | TEXT NOT NULL | `pending` / `confirmed` / `skipped` |
| market | TEXT NOT NULL | `A` or `QDII` |
| shares | TEXT | 确认后份额 |
| nav | TEXT | 用于确认的净值（定价日 NAV） |
| remark | TEXT | 备注 |
| confirm_date | TEXT NOT NULL | 根据市场 `get_confirm_date` 预先写入，便于 SQL 过滤 |

### navs
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| fund_code | TEXT NOT NULL |
| day | TEXT NOT NULL |
| nav | TEXT NOT NULL |
| PRIMARY KEY | (fund_code, day) |

### dca_plans
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| fund_code | TEXT PRIMARY KEY |
| amount | TEXT NOT NULL |
| frequency | TEXT NOT NULL | `daily` / `weekly` / `monthly` |
| rule | TEXT NOT NULL | 周期规则（MON..SUN / 1..31） |

### alloc_config
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| asset_class | TEXT PRIMARY KEY |
| target_weight | TEXT NOT NULL | 0..1 Decimal |
| max_deviation | TEXT NOT NULL | 允许偏离（0..1） |

### meta（可选）
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| key | TEXT PRIMARY KEY |
| value | TEXT NOT NULL | 版本、迁移标识等 |

当前仅记录 `schema_version`。如需迁移，可在 helper 初始化时读取/对比该值。
