# 开发决策记录

> 本文档记录关键架构与业务决策。
> 完整规则见 `docs/settlement-rules.md` / `docs/architecture.md`。

---

## 2025-11-21 v0.3.1 架构简化（渐进式重构）

### 背景与动机

在完成 v0.3 日历与接口重构后，团队评估了当前 DDD 4层架构（Jobs → Wiring → Usecases → Adapters → Core）的复杂度：
- **单人开发**：依赖注入容器（`DependencyContainer`）和 wiring 层对单人维护来说是过度抽象
- **AI 准备**：规划在 v1.x 引入 AI 辅助决策，需要让业务逻辑"可调用"（函数而非类）
- **心智负担**：从 Job 到实际业务逻辑需要穿越 5 个概念层（Job → Container → UseCase → Protocol → Adapter）

参考业界"渐进式架构"实践，决定采用"先简化，后演进"策略：
- **当前阶段（v0.3.1）**：删除 wiring，业务流程用函数封装在 jobs 里
- **未来阶段（v1.0）**：将业务函数移到 `app/flows/` 层，供 AI 工具调用

### 完成内容

**架构简化**：
- 删除 `src/app/wiring.py` 和 `DependencyContainer` 类
- 删除 `src/core/protocols.py`（不再使用 Protocol 抽象）
- Jobs 层直接构造具体 Repo 类（如 `SqliteTradeRepo(conn, calendar)`）
- 业务流程用函数封装（如 `confirm_trades_flow()`），物理上在 `jobs/` 文件里

**UseCase 层改造**：
- 保留 `src/usecases/` 目录和业务逻辑
- 逐步从"UseCase 类 + execute() 方法"改为"纯函数 + Result dataclass"
- 参数类型从 Protocol 改为具体类（如 `TradeRepo` → `SqliteTradeRepo`）
- 保持业务语义和方法签名不变

**Repo 层简化**：
- 删除所有 `: Protocol` 继承声明
- 删除类型注解中的 Protocol 引用
- 保持方法签名和实现逻辑完全不变

**不变部分**（保持稳定）：
- Schema v3 不变（不新增表/字段）
- `src/core/` 领域模型（dataclass、纯函数）不变
- `src/adapters/` Repo 实现逻辑不变
- 业务规则（settlement/rebalance 等）不变

### 决策

**为什么删除 wiring 层和 Protocol 抽象？**
- **wiring 层**：依赖注入容器适合"多团队、多实现切换"场景，但当前是单人维护、单 DB 实现
- **Protocol 抽象**：主要服务于接口替换和测试 mock，但当前：
  - 只有一个 DB 实现（SQLite），不会切换到 PostgreSQL/MySQL
  - 不做单元测试（v0.3.1 阶段不引入测试框架）
  - Protocol 增加了"找定义"的跳转层级（先跳到 Protocol，再跳到具体类）
- Jobs 直接构造具体类（`repo = SqliteTradeRepo(conn, calendar)`）更直观
- 具体类的方法签名本身就是"接口约定"，不需要额外的 Protocol 定义
- 减少两层抽象（wiring + Protocol），降低心智负担

**为什么暂时保留 usecases？**
- 业务逻辑已经在 usecases 里沉淀，不宜一次性大改
- 采用"逐步函数化"策略：先把 `UseCase.execute()` 改为普通函数
- 未来 v1.0 时再统一移到 `app/flows/` 供 AI 调用

**为什么用"函数封装流程"而非立刻建 flows/ 目录？**
- v0.4 之前不会引入 AI，提前建 `app/flows/` 是过度设计
- 在 jobs 里用函数封装（如 `confirm_trades_flow()`）已经达到"逻辑复用"目标
- v1.0 时只需"剪切-粘贴"这些函数到新目录，重构成本很低

**架构演进路径**：
```
v0.3（当前）:   Jobs → Wiring → UseCase 类(依赖 Protocol) → Repo(实现 Protocol)
v0.3.1（目标）: Jobs (含 flow 函数) → UseCase 函数 → 具体 Repo 类
v1.0（未来）:   Jobs → app/flows/ ← AI tools/ → 具体 Repo 类
```

**类型系统变化**：
```python
# v0.3（有 Protocol）
def confirm_trades(trade_repo: TradeRepo, nav_provider: NavProtocol) -> ConfirmResult:
    ...

# v0.3.1（无 Protocol）
def confirm_trades(trade_repo: SqliteTradeRepo, nav_service: LocalNavService) -> ConfirmResult:
    ...
```

### 影响范围

- 删除文件：
  - `src/app/wiring.py`（约 150 行）
  - `src/core/protocols.py`（约 210 行）
- 修改文件：
  - 所有 `src/jobs/*.py`（约 10 个文件，删除 container 调用）
  - 所有 `src/adapters/db/sqlite/*.py`（约 8 个 Repo 文件，删除 Protocol 继承）
  - 所有 `src/adapters/datasources/*.py`（约 3 个 Service 文件，删除 Protocol 继承）
  - 所有 `src/usecases/**/*.py`（约 15 个 UseCase，改参数类型和调用方式）
- 文档更新：`docs/architecture.md`、`docs/roadmap.md`、`docs/coding-log.md`

### 未来规划

**v1.0 AI 阶段（远期）**：
- 新建 `app/flows/` 目录，将业务函数从 jobs 移入
- 新建 `ai/tools/` 目录，封装供 LLM Function Calling 的工具函数
- Jobs 变薄：只做参数解析，调用 flows
- AI 调用 flows，生成 ActionLog/Snapshot（届时再引入相关表）

> 详细规划见 `docs/roadmap.md` v0.3.1 和 v1.x 章节。

---

## 2025-11-19 v0.3 日历与接口重构

### 完成内容

**核心接口统一到 `src/core/protocols.py`**：
- 新建 `src/core/fund.py`，将 `FundInfo` 数据类从 ports 迁移到核心层
- 新建 `src/core/protocols.py`，集中定义所有接口（Protocol）
- 删除 `src/usecases/ports.py`，完成接口层从 usecases 到 core 的迁移
- 接口命名规范化：
  - Repository 接口：保持 `*Repo`（如 `TradeRepo`）
  - Service 接口：使用 `*Protocol` 后缀（如 `NavProtocol` / `NavSourceProtocol` / `ReportProtocol` / `CalendarProtocol`）

**日历子系统收敛**：
- 统一日历协议：`CalendarProtocol` 提供 `is_open` / `next_open` / `shift` 三个方法
- 合并实现：`DbCalendarService` 整合了原 `SqliteTradingCalendar` + `DateMathService` + `SqliteCalendarStore` 的所有逻辑
- 删除冗余文件 4 个：`calendar.py` / `date_math.py` / `calendar_store.py` / `trading_calendar.py`
- **严格模式**：v0.3 起强制要求使用 DB 交易日历，删除工作日近似 fallback，缺失数据时直接抛错

**Service/Repo 实现命名统一**：
- `LocalNavProvider` → `LocalNavService`（实现 `NavProtocol`）
- `EastmoneyNavProvider` → `EastmoneyNavService`（实现 `NavSourceProtocol`）
- `DiscordReportSender` → `DiscordReportService`（实现 `ReportProtocol`）

**依赖注入简化**：
- `DependencyContainer` 删除 `calendar_store` / `date_math` 字段
- 统一使用 `self.calendar: CalendarProtocol` 作为唯一日历服务
- `SqliteTradeRepo` 构造函数简化为 `__init__(conn, calendar)`

### 决策

- **接口分层明确**：核心接口在 `core/protocols.py`，领域数据类在 `core/`，杜绝 usecases 层定义接口
- **NAV 接口拆分**：
  - `NavProtocol`：运行时本地查询（确认、日报、再平衡）
  - `NavSourceProtocol`：外部数据源抓取（HTTP、CSV 等）
  - 明确职责边界，避免混用
- **日历严格模式**：v0.3 起不再允许"工作日近似"作为 fallback，必须通过 `sync_calendar` / `patch_calendar` 维护完整日历数据
- **calendar_key 设计**：使用灵活的字符串标识（如 "CN_A" / "US_NYSE"），不绑定到 `MarketType` 枚举，保持扩展性

### 影响范围

- 更新文件：17 个 UseCase / 6 个 Adapter / 3 个核心模块 / wiring.py / settlement.py
- 删除文件：4 个旧日历实现 + 1 个 ports.py
- 新增文件：2 个（core/fund.py + core/protocols.py）+ 1 个（adapters/db/sqlite/calendar.py）

---

## 2025-11-19 交易日历架构升级（策略化）与 Schema v3

### 完成内容

**SettlementPolicy 引入**：
- 新增 `src/core/trading/policy.py`，定义 `SettlementPolicy` 数据类：
  - `guard_calendar`：卫兵日历（如 QDII 用 CN_A 作为门户日历，过滤国内节假日）
  - `pricing_calendar`：定价日历（决定 pricing_date，A 股用 CN_A，QDII 用 US_NYSE）
  - `count_calendar`：计数日历（决定 T+N 如何数，QDII 用 US_NYSE）
  - `settle_lag`：确认偏移量（A=1，QDII=2）
- 替代原 `src/core/trading/settlement.py` 中的简单 lag 规则

**DateMath 日历键灵活化**：
- `src/core/trading/date_math.py` 中的 `DateMath` 改为基于命名日历键（"CN_A" / "US_NYSE"）工作
- 支持单市场策略（A 股）与组合策略（QDII 卫兵 + 定价 + 计数）

**pricing_date 持久化（Schema v3）**：
- `trades` 表增加 `pricing_date` 字段（NOT NULL）
- 创建交易时调用 SettlementPolicy 计算并持久化 pricing_date
- 确认时严格按 `trades.pricing_date` 读取 NAV，不再运行时重算
- schema_version 升级到 3

**CalendarStore 严格模式**：
- `src/adapters/db/sqlite/calendar_store.py` 中的 `SqliteCalendarStore` 查缺即报错
- 杜绝"工作日近似"误判（v0.2 的 SimpleTradingCalendar fallback 已删除）

**日历数据源**：
- 注油：`exchange_calendars`（仅到"日历最大已知日期"）
- 修补：`Akshare`（新浪，在线"以真覆假"，仅到"数据源最大已知日期"）

### 决策

- **卫兵 + 定价 + 计数分离**：QDII 场景下，国内节假日、美股开市日、T+N 计数规则三者解耦，避免"简单 T+2"的认知误区
- **定价日入库**：`pricing_date` 持久化，确认严格按该日 NAV；便于可追溯与幂等
- **严格模式**：日历查缺即报错，强制完整数据；配合 `sync_calendar` / `patch_calendar` 维护

> 交易日历与确认规则的完整定义见 `docs/settlement-rules.md`。

---

## 2025-11-22 日报展示日与区间抓取（v0.2 严格）

### 完成内容

**展示日逻辑**：
- 日报/状态视图默认展示日 = 上一交易日（当前按"上一工作日"近似）
- CLI 支持 `--as-of YYYY-MM-DD` 指定任意展示日
- 严格口径：只用指定展示日的 NAV，缺失则剔除该基金，文末提示"总市值可能低估"

**区间抓取 Job**：
- 新增 `src/jobs/fetch_navs_range.py`，支持 `--from` / `--to` 参数
- 闭区间逐日抓取（严格只抓指定日，不做回退）
- 幂等 upsert，失败清单在任务末尾汇总打印

**视图切换**：
- `status` / `daily_report` 支持 `--mode market|shares` 切换
- 市值视图：依赖 NAV，严格不回退
- 份额视图：不依赖 NAV，作为兜底

### 决策

- **展示日与抓取分离**：抓取是 HTTP 职责，报表是只读本地数据
- **严格不回退**：对选定展示日，仅使用该日 NAV；缺失即剔除，不用"最近交易日 NAV"回退
- **兜底视图**：NAV 不全时用份额视图，明确告知用户"非市值口径"

> 日报展示日、NAV 严格口径与再平衡触发条件的完整规则见 `docs/settlement-rules.md`。

---

## 2025-11-19 NAV 策略 v0.2（严格版）

### 完成内容

**确认用 NAV**：
- 仅使用"定价日 NAV"（`pricing_date = next_trading_day_or_self(trade_date)`）
- `ConfirmPendingTrades` 在定价日 NAV 缺失或 `<= 0` 时直接跳过，保留为 pending，后续可重试
- 不做任何回退（不用"上一交易日 NAV"或"下一交易日 NAV"）

**报表/状态视图用 NAV**：
- 仅使用"当日 NAV"（`day = date.today()` 或 `--as-of` 指定日）
- 当日 NAV 缺失或 `<= 0` 的基金不计入当日市值与权重
- 在"NAV 缺失"区块列出基金代码
- 不做"最近交易日 NAV"回退；报告文案提示"总市值可能低估"

### 决策

- **严格口径最大程度贴合官方净值时间口径**，避免引入灰色估值与难以解释的回退规则
- 未来若引入"柔性回退视图"，将以新版本（v0.3+）提供独立开关与清晰标注，不影响 v0.2 的严格口径

> NAV 策略 v0.2 的完整规则定义见 `docs/settlement-rules.md`。

---

## 2025-11-18 交易确认规则 v0.2（TradingCalendar + 定价日）

### 完成内容

**确认规则切换为"定价日 + lag"**：
- 接口：`get_confirm_date(market, trade_date, calendar)`（纯函数），`TradingCalendar`（协议）
- 定价日：`pricing_date = calendar.next_trading_day_or_self(trade_date)`
- 确认日：`confirm_date = calendar.next_trading_day(pricing_date, offset=lag)`
- 确认 lag：`A=1`、`QDII=2`（不做基金级覆盖）

**交易日历实现**：
- `SimpleTradingCalendar`（仅周末为非交易日，不含节假日表）
- 引入 `trading_calendar` 表结构，为 v0.3 的 DB 日历做准备

**NAV 使用（确认用例）**：
- 仅取 `pricing_date` 的官方净值
- 若缺失或 `<=0`，则跳过待重试

### 差异说明

相比 v0.1（基于 `trade_date + lag` 再周末顺延），当"下单日在周末"时：
- A 基金确认日落在下周二（更符合"定价日=T+1"的实务口径）
- QDII 基金确认日随之后移（定价日+2）

### 决策

- **定价日优先**：先确定定价日，再计算 T+N
- **日历可替换**：通过 Protocol 注入，v0.3 可切换为 DB 日历
- **严格 NAV 口径**：缺失不做回退，保留待重试

> 交易确认规则的完整定义见 `docs/settlement-rules.md`。

---

## 2025-11-20 外部 NAV 接入与 UseCase 抽取

### 完成内容

**NAV 数据流分离**：
- `EastmoneyNavProvider`：从东方财富 API 抓取官方净值（HTTP）
- `SqliteNavRepo`：本地 `navs` 表存储（upsert 幂等）
- `LocalNavProvider`：仅从本地 `navs` 表读取 NAV（供确认/日报/再平衡使用）

**UseCase 抽取**：
- 新增 `FetchNavsForDay`：遍历 `funds` 表，调用 `EastmoneyNavProvider` 抓取指定日 NAV，写入本地
- 新增 `src/jobs/fetch_navs.py`：对外 Job 入口

**请求头优化**：
- 固定 `User-Agent`、`Referer: https://fundf10.eastmoney.com/`、`Accept: application/json`，减少 403 风险

### 决策

- **抓取与报表职责分离**：HTTP 抓取在 Job 层，确认/日报只读本地
- **幂等 upsert**：NAV 数据按 `(fund_code, day)` 幂等写入，支持重跑
- **失败汇总**：获取失败或 NAV 无效时记录清单，Job 结束时统一打印

---

## 2025-11-19 再平衡建议 v0.2（基础版）

### 完成内容

**阈值来源**：
- 优先使用 `alloc_config.max_deviation`（按资产类别）
- 未配置时使用默认 5% 阈值（0.05）

**触发条件**：
- 当 `|实际权重 - 目标权重| > 阈值` 时，给出"增持/减持"建议
- 否则标注为"观察（hold）"

**建议金额算法**：
- `建议金额 = 总市值 × |偏离| × 50%`（渐进式，保守），仅用于提示
- 正偏离（超配）→ 减持；负偏离（低配）→ 增持

**口径与限制**：
- 权重与总市值与"市值版日报"一致：仅使用当日 NAV、已确认份额、不回退
- 不考虑交易成本、最小申赎份额与税费
- 不拆分到具体基金层面（只到资产类别）

### 决策

- **基础版粒度**：只到资产类别，不拆具体基金
- **保守建议**：50% 偏离修正，避免过度交易
- **与日报一致**：严格 NAV 口径，缺失即剔除

> 再平衡规则的完整定义见 `docs/settlement-rules.md`。
