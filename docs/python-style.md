# Python 代码规范（MVP）

> 基础编码规范（类型注解、Decimal 使用、Docstring、模块组织等）详见 `.claude/skills/code-style/SKILL.md`。
> 本文档仅记录项目特有的命名规范、精度规则与架构约束。

## 精度与舍入规则

- 金额：2 位小数
- 净值：4 位小数
- 份额：4 位小数

## 架构与错误处理

- 目录职责：
  - `core` 仅含纯领域逻辑，不依赖外部库实现
  - `usecases` 仅依赖 `core` 与 `ports`（Protocol）
  - `adapters` 实现具体技术，供 `app/wiring` 装配
  - `jobs` 仅做参数解析与调用 usecase，不写业务
- 错误处理：核心抛异常；入口捕获并 `print`
- 日志：使用 `app/log.py` 的 `log()`；不引 logging 框架
- SQL 打印：通过 SQLite trace 回调；可用 `ENABLE_SQL_DEBUG` 控制

## 类型约束补充

- 核心层（`src/core`、`src/usecases`）**禁止使用 `Any`**；适配层仅允许在外部边界短暂出现 `Any`
- 固定结构优先使用 `@dataclass(slots=True)` 或 `TypedDict`，避免 `dict[str, Any]` 黑箱容器
- 封闭取值域使用 `Literal[...]` 或枚举（如 `AssetClass`/`TradeStatus`）
- 对外依赖统一走 `Protocol`，UseCase 仅依赖端口与领域模型

## 接口与实现命名规范（v0.3）

### 核心原则

- 接口（Protocol）统一定义在 `src/core/protocols.py`
- 领域数据类放在 `src/core/{domain}.py`

### 命名规则

| 类型 | 命名规则 | 示例 |
|-----|---------|------|
| Repository 接口 | `{Domain}Repo` | `TradeRepo`, `NavRepo` |
| Service 接口 | `{Domain}Protocol` | `NavProtocol`, `CalendarProtocol` |
| Repository 实现 | `{Tech}{Domain}Repo` | `SqliteTradeRepo` |
| Service 实现 | `{Tech}{Domain}Service` | `LocalNavService`, `EastmoneyNavService` |

### 文件位置

```
src/core/protocols.py                    → 所有 Protocol 接口
src/core/fund.py                         → FundInfo 数据类
src/core/policy.py                       → SettlementPolicy 数据类
src/adapters/db/sqlite/trade_repo.py     → SqliteTradeRepo
src/adapters/datasources/local_nav.py    → LocalNavService
src/adapters/db/sqlite/calendar.py       → DbCalendarService
```

### 职责分离示例

- `NavProtocol`：运行时本地查询（确认、日报、再平衡）
- `NavSourceProtocol`：外部数据源抓取（HTTP、CSV）
- `CalendarProtocol`：交易日历查询与 T+N 偏移计算

## 函数与 UseCase 命名规范

### 函数命名动词白名单

| 动词 | 含义 | 示例 |
|------|------|------|
| `calc_` | 纯计算，无副作用 | `calc_pricing_date()`, `calc_weight_diff()` |
| `get_` | 本地/DB 查询（快速） | `get_fund()`, `get_nav()` |
| `fetch_` | 外部获取（IO 操作） | `fetch_navs()` |
| `list_` | 列表查询 | `list_funds()`, `list_pending_to_confirm()` |
| `add_` | 新增实体 | `add_fund()`, `add(trade)` |
| `update_` | 更新实体 | `update(trade)` |
| `upsert_` | 插入或更新（幂等） | `upsert(nav)` |
| `build_` | 构造结构化数据 | `build_rebalance_advice()` |
| `render_` | 渲染文本 | `render(report)` |
| `quantize_` | 精度处理 | `quantize_amount()` |

### UseCase 类命名白名单

| 动词 | 含义 | 是否持久化 | 示例 |
|------|------|-----------|------|
| `Create` | 创建并保存实体 | ✅ 是 | `CreateTrade` |
| `Make` | 临时生成数据/报告 | ❌ 否 | `MakeDailyReport`, `MakeRebalance` |
| `Fetch` | 从外部获取数据 | ❌ 否 | `FetchNavs` |
| `Run` | 执行流程/批处理 | ✅ 可能 | `RunDailyDca` |
| `Confirm` | 确认业务状态 | ✅ 是 | `ConfirmTrades` |
| `Skip` | 跳过某项操作 | ✅ 是 | `SkipDca` |

**判断标准**：
- 如果 UseCase 内部调用 `repo.add()` → 用 `Create`
- 如果只是组装数据后发送/返回 → 用 `Make`
- 如果从外部 IO 获取 → 用 `Fetch`

### UseCase 结果类命名规范

**统一后缀**：所有 UseCase 返回的数据类使用 `Result` 后缀

**命名原则**：
1. **去冗余**：类名不重复字段名中的关键词
   ```python
   # ❌ 错误：Suggestion 重复
   class RebalanceSuggestionResult:
       suggestions: list[RebalanceAdvice]

   # ✅ 正确：简洁无冗余
   class RebalanceResult:
       suggestions: list[RebalanceAdvice]
   ```

2. **保持简洁**：控制在 15 字符左右
   - ✅ `ConfirmResult` (13)
   - ✅ `FetchNavsResult` (15)
   - ✅ `RebalanceResult` (15)
   - ✅ `ReportResult` (12)

3. **与 UseCase 对齐**：
   - `MakeDailyReport` → `ReportResult`
   - `MakeRebalance` → `RebalanceResult`
   - `FetchNavs` → `FetchNavsResult`
   - `ConfirmTrades` → `ConfirmResult`

## Docstring 补充说明

- 类/UseCase/Protocol 必须写 docstring；公开方法建议写，简单工具函数可省略
- 复杂参数或有副作用时使用 `Args:` / `Returns:` 块说明业务语义

## Import 顺序

使用 `ruff check --fix .` 自动维护。
