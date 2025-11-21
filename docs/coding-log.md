# 开发决策记录

> 本文档记录关键架构与业务决策。
> 完整规则见 `docs/settlement-rules.md` / `docs/architecture.md`。

---

## 2025-11-22 v0.3.1 架构简化与目录重构

### 完成内容

**目录结构重组**：
- `jobs/` → `cli/`：命令行入口脚本
- `usecases/` → `flows/`：业务流程类（8 个类合并到 4 个文件）
  - `flows/trade.py`：CreateTrade + ConfirmTrades
  - `flows/dca.py`：RunDailyDca + SkipDca
  - `flows/market.py`：FetchNavs
  - `flows/report.py`：MakeDailyReport + MakeRebalance + MakeStatusSummary
- `adapters/` → `data/`：数据访问层
  - `data/db/`：数据库 Repo（扁平化，去除 sqlite/ 子目录）
  - `data/client/`：外部客户端（原 datasources/ + notify/）
- `app/` → `core/`：配置和日志移入核心层
- `core/` 内部重组：
  - `core/models/`：领域数据类（Trade, Fund, DcaPlan, AssetClass, Policy）
  - `core/rules/`：纯业务规则函数（settlement, rebalance, precision）

**删除抽象层**：
- 删除 `src/core/protocols.py`（210 行 Protocol 定义）
- 删除 `src/app/wiring.py`（150 行 DependencyContainer）
- 所有 Repo/Service 类去除 Protocol 继承

**类名简化**：
- `SqliteTradeRepo` → `TradeRepo`
- `SqliteFundRepo` → `FundRepo`
- `SqliteNavRepo` → `NavRepo`
- `SqliteDcaPlanRepo` → `DcaPlanRepo`
- `SqliteAllocConfigRepo` → `AllocConfigRepo`
- `DbCalendarService` → `CalendarService`
- `SqliteDbHelper` → `DbHelper`
- `EastmoneyNavService` / `LocalNavService` / `DiscordReportService`（保持不变）

**Flow 函数模式**：
- CLI 文件中采用 `xxx_flow()` 函数封装业务逻辑
- 直接实例化具体 Repo 类：`TradeRepo(conn, calendar)`
- 示例：
  ```python
  def confirm_trades_flow(day: date) -> ConfirmResult:
      db = DbHelper()
      conn = db.get_connection()
      calendar = CalendarService(conn)
      trade_repo = TradeRepo(conn, calendar)
      nav_repo = NavRepo(conn)
      nav_service = LocalNavService(nav_repo)
      usecase = ConfirmTrades(trade_repo, nav_service)
      return usecase.execute(today=day)
  ```

**Import 路径更新**：
- `from src.core.trade import` → `from src.core.models.trade import`
- `from src.core.trading.settlement import` → `from src.core.rules.settlement import`
- `from src.adapters.db.sqlite.trade_repo import` → `from src.data.db.trade_repo import`
- `from src.app.log import` → `from src.core.log import`
- `from src.usecases.trading.create_trade import` → `from src.flows.trade import`

### 决策

**删除 Protocol 和 DI 的理由**：
- 单 DB 实现（只有 SQLite），不需要多实现抽象
- Protocol 主要服务于依赖注入和测试 mock，当前不做单元测试
- 减少类型系统复杂度，降低"找定义"的跳转次数
- 具体类的方法签名已经是"接口约定"，不需要额外的 Protocol 层

**目录结构设计原则**：
- **cli/**：纯入口，只做参数解析和流程调用
- **flows/**：业务逻辑，包含多个相关 Flow 类的文件
- **core/**：纯核心，无外部依赖（只有 models + rules + config/log）
- **data/**：外部交互，DB 和 HTTP 统一为"数据访问"

**合并 UseCase 的策略**：
- 按业务域合并：trading、dca、market、report
- 保持类的独立性，只是放在同一文件
- 避免单文件单类的碎片化

### 影响范围

- 更新文件：41 个 Python 文件
- 重命名类：7 个 Repo/Service 类
- 合并 UseCase：8 个类 → 4 个文件
- 删除文件：2 个（protocols.py + wiring.py）
- 新目录：cli/, flows/, data/

### 验证结果

- ✅ Ruff 检查：全部通过
- ✅ 数据库初始化：成功
- ✅ CLI 命令：`python -m src.cli.dca` / `python -m src.cli.confirm` 正常运行
- ✅ Schema 版本：保持 v3 不变

---

## 2025-11-19 v0.3 日历与接口重构

### 完成内容

**核心接口统一到 `src/core/protocols.py`**：
- 新建 `src/core/fund.py`，将 `FundInfo` 数据类从 ports 迁移到核心层
- 新建 `src/core/protocols.py`，集中定义所有接口（Protocol）
- 删除 `src/usecases/ports.py`
- 接口命名规范化：
  - Repository：`*Repo`（如 `TradeRepo`）
  - Service：`*Protocol` 后缀（如 `NavProtocol`, `CalendarProtocol`）

**日历子系统收敛**：
- 统一日历协议：`CalendarProtocol`（`is_open` / `next_open` / `shift`）
- 合并实现：`DbCalendarService` 整合原有 4 个文件的逻辑
- **严格模式**：v0.3 起强制使用 DB 交易日历，缺失数据时直接抛错

**SettlementPolicy 引入**：
- 新增 `src/core/trading/policy.py` 定义策略数据类
- 三层日历组合：`guard_calendar` / `pricing_calendar` / `lag_counting_calendar`
- 支持 QDII 场景：CN_A 卫兵 + US_NYSE 定价/计数

**pricing_date 持久化（Schema v3）**：
- `trades` 表增加 `pricing_date` 字段（NOT NULL）
- 创建交易时计算并持久化
- 确认时严格按 `pricing_date` 读取 NAV

### 决策

- **接口分层明确**：核心接口在 `core/protocols.py`，杜绝 usecases 层定义接口
- **NAV 接口拆分**：`NavProtocol`（运行时查询）vs `NavSourceProtocol`（外部抓取）
- **日历严格模式**：不允许"工作日近似"fallback
- **卫兵 + 定价 + 计数分离**：QDII 场景下三者解耦

---

## 2025-11-19 交易确认延迟追踪（v0.2.1）

### 完成内容

**延迟标记机制**：
- `trades` 表增加字段：
  - `confirmation_status`：normal / delayed
  - `delayed_reason`：nav_missing / ...
  - `delayed_since`：首次延迟日期
- 确认逻辑：
  1. `today < confirm_date` → 正常等待
  2. `today >= confirm_date` 且 NAV 存在 → 确认
  3. `today >= confirm_date` 且 NAV 缺失 → 标记 delayed

**日报展示**：
- 新增"交易确认情况"板块：
  - ✅ 已确认（最近 5 笔）
  - ⏳ 待确认（显示剩余天数）
  - ⚠️ 异常延迟（显示延迟原因和建议）

**自动恢复**：
- 补充 NAV 后再次运行确认任务自动确认
- 确认成功后清除延迟标记

### 决策

- 延迟标记字段与 `status` 字段正交：`status=pending` + `confirmation_status=delayed`
- 提供建议文案：
  - 延迟 ≤2 天：等待 1-2 个工作日
  - 延迟 >2 天：检查支付宝订单状态

---

## 2025-11-18 日报展示日与区间抓取（v0.2 严格）

### 完成内容

**展示日逻辑**：
- 日报/状态视图默认展示日 = 上一交易日
- CLI 支持 `--as-of YYYY-MM-DD` 指定展示日
- **严格不回退**：只用展示日 NAV，缺失则跳过并提示

**NAV 严格口径**：
- 确认用定价日 NAV
- 日报/status 仅用当日 NAV
- NAV ≤0 或缺失 → 不计入市值，文末提示"总市值可能低估"

**区间抓取**：
- 新增 Job：`fetch_navs_range --from D1 --to D2`
- 遍历日期区间调用 `FetchNavs`
- 汇总成功/失败统计

### 决策

- **严格口径**：不做"最近可用 NAV"回退，避免误导
- **透明提示**：日报明确告知 NAV 缺失情况
- **份额视图兜底**：NAV 缺失时可用 `--mode shares` 查看配置偏离

---

> **历史决策归档**：更早期的决策（v0.1 MVP、v0.2 基础功能）已移至归档，保留 v0.2.1 以后的关键记录。
