# 开发决策记录

> 本文档记录关键架构与业务决策。
> 完整规则见 `docs/settlement-rules.md` / `docs/architecture.md`。

---

## 2025-11-22 v0.3.2 配置管理 CLI（闭环完成）

### 完成内容

**问题定位**：
- v0.3.1 完成架构重构后，发现用户必须直接操作数据库才能配置基金、定投计划、资产配置
- 破坏了"命令行工具"的定位，无法形成完整业务闭环

**解决方案**：
- 新建 4 个配置管理 CLI 模块（共 ~400 行）
- 补全仓储层的 upsert/list 方法（~100 行）
- 新建 Flow 层配置管理函数（~200 行）

**新增文件**：
- `src/flows/config.py`：8 个配置管理 Flow 函数
  - 基金管理：`add_fund()` / `list_funds()`
  - 定投计划：`add_dca_plan()` / `list_dca_plans()` / `disable_dca_plan()` / `enable_dca_plan()`
  - 资产配置：`set_allocation()` / `list_allocations()`
- `src/flows/trade.py`：新增 `list_trades()` 函数
- `src/cli/fund.py`：基金配置 CLI（add/list 子命令）
- `src/cli/dca_plan.py`：定投计划 CLI（add/list/disable/enable 子命令）
- `src/cli/alloc.py`：资产配置 CLI（set/show 子命令）
- `src/cli/trade.py`：手动交易 CLI（buy/sell/list 子命令）
- `src/core/models/alloc_config.py`：AllocConfig 数据类

**仓储层增强**：
- `DcaPlanRepo`：新增 `upsert_plan()` / `set_status()` / `list_all()` / `list_active()`
- `AllocConfigRepo`：新增 `set_alloc()` / `list_all()`
- `TradeRepo`：新增 `list_by_status()`
- `FundRepo`：确认已有 `add_fund()` upsert 支持

**Schema 变更**（v3 → v3，无版本号变化）：
- `dca_plans` 表增加 `status TEXT NOT NULL DEFAULT 'active'` 字段
- 向后兼容：`_row_to_plan()` 使用 `row.get("status", "active")` 兼容旧数据

**依赖注册修正**：
- `container.py`：`alloc_repo` 重命名为 `alloc_config_repo`（与 Flow 参数名一致）

### 决策

**CLI 设计原则**：
- **子命令模式**：每个 CLI 文件支持多个子命令（add/list/set/show 等）
- **职责单一**：每个 CLI 只负责参数解析和结果展示，业务逻辑在 Flow 层
- **用户友好**：
  - 使用有意义的参数名（`--fund` / `--class` / `--target`）
  - 提供清晰的错误提示（参数验证、计划不存在等）
  - 显示操作结果摘要（如 `alloc show` 提示总权重是否为 100%）

**定投计划状态管理**：
- 新增 `status` 字段（active/disabled）：支持临时禁用而不删除配置
- 新增 `enable_dca_plan()` 函数：对称设计（disable/enable 成对）
- 理由：用户可能短期暂停定投，后续恢复，无需重新配置

**交易查询策略**：
- `list_trades(status=None)` 合并所有状态（pending/confirmed/skipped）
- 按 trade_date 降序排列（最新交易在前）
- 理由：避免为"查询所有交易"单独添加 `TradeRepo.list_all()` 方法

**命名规范统一**：
- Flow 函数：`snake_case`（如 `add_fund()` / `set_allocation()`）
- CLI 子命令：`kebab-case`（如 `dca_plan add` / `alloc show`）
- Repo 方法：`snake_case`（如 `upsert_plan()` / `list_all()`）

### 影响范围

- 新增文件：7 个（1 个 Model + 1 个 Flow + 4 个 CLI + 1 个 __init__）
- 修改文件：5 个 Repo + 1 个 Flow + 1 个 container + 2 个 docs
- Schema 变更：1 个字段（dca_plans.status）
- 代码增量：~700 行
- 文档更新：`operations-log.md` 新增完整 v0.3.2 CLI 用法示例

### 验证结果

- ✅ Ruff 检查：全部通过（自动修复 2 处 import 顺序）
- ✅ CLI 用法：operations-log.md 已更新示例
- ✅ 业务闭环：用户可完全通过 CLI 完成配置 → 定投 → 确认 → 报表流程

### 用户体验对比

**重构前**（v0.3.1）：
```bash
# ❌ 必须直接操作数据库
sqlite3 data/portfolio.db "INSERT INTO funds VALUES ('000001', '华夏成长', 'CSI300', 'CN_A');"
sqlite3 data/portfolio.db "INSERT INTO dca_plans VALUES ('000001', '1000', 'monthly', '1');"
```

**重构后**（v0.3.2）：
```bash
# ✅ 使用统一的 CLI
python -m src.cli.fund add --code 000001 --name "华夏成长" --class CSI300 --market CN_A
python -m src.cli.dca_plan add --fund 000001 --amount 1000 --freq monthly --rule 1
python -m src.cli.alloc set --class CSI300 --target 0.6 --deviation 0.05
```

---

## 2025-11-22 v0.3.1 依赖注入重构（阶段 2）

### 完成内容

**Flow 层函数化**：
- 将所有 Flow 业务类改为纯函数：
  - `CreateTrade` → `create_trade()`
  - `ConfirmTrades` → `confirm_trades()`
  - `RunDailyDca` → `run_daily_dca()`
  - `MakeDailyReport` → `make_daily_report()`
  - `FetchNavs` → `fetch_navs()`
  - 等 8 个函数（分布在 4 个文件）

**依赖注入装饰器**：
- 新建 `src/core/dependency.py`（170 行）：
  - `@register(name)`：注册工厂函数到容器
  - `@dependency`：自动注入函数参数（类似 FastAPI `Depends()`）
  - `get_registered_deps()`：查看已注册依赖（调试用）
- 新建 `src/core/container.py`（200 行，原 `deps.py`）：
  - 集中管理 9 个依赖工厂函数
  - 单例数据库连接：`get_db_connection()`
  - Repo 工厂：`get_trade_repo()`, `get_nav_repo()` 等
  - Service 工厂：`get_local_nav_service()`, `get_discord_report_service()` 等

**CLI 层简化**：
- 移除所有手动依赖实例化代码
- 从 `xxx_flow()` 函数改为直接调用 Flow 函数
- 示例：
  ```python
  # 重构前（>100 行）
  def confirm_trades_flow(day: date):
      db = DbHelper()
      conn = db.get_connection()
      calendar = CalendarService(conn)
      trade_repo = TradeRepo(conn, calendar)
      nav_service = LocalNavService(NavRepo(conn))
      usecase = ConfirmTrades(trade_repo, nav_service)
      return usecase.execute(today=day)

  # 重构后（~60 行）
  result = confirm_trades(today=day)  # 一行调用
  ```

**模块重命名**：
- `src/core/injector.py` → `src/core/dependency.py`
- `src/core/deps.py` → `src/core/container.py`

### 决策

**采用装饰器依赖注入的理由**：
- **代码简洁**：移除 ~40% 的 CLI 样板代码
- **类型安全**：保持完整的类型注解和 IDE 支持
- **测试友好**：可以轻松传入 Mock 对象覆盖依赖
- **可维护性**：集中管理依赖创建逻辑
- **Pythonic**：函数式 + 装饰器优于 Java 风格的类

**依赖注入设计原则**：
- **显式注册**：所有可注入依赖必须通过 `@register` 显式注册
- **命名一致**：注册名必须与函数参数名完全一致
- **可覆盖**：调用时传入的非 None 参数不会被覆盖

**Flow 函数签名规范**：
```python
@dependency
def confirm_trades(
    *,
    today: date,  # 业务参数（必填）
    trade_repo: TradeRepo | None = None,  # 依赖参数（自动注入）
    nav_service: LocalNavService | None = None,  # 依赖参数（自动注入）
) -> ConfirmResult:
    # trade_repo 和 nav_service 已自动注入，直接使用
    to_confirm = trade_repo.list_pending_to_confirm(today)
    ...
```

### 影响范围

- 更新文件：13 个 Python 文件（8 个 Flow + 5 个 CLI）
- 新增文件：2 个（`dependency.py` + `container.py`）
- 重命名文件：2 个（`deps.py` → `container.py`, `injector.py` → `dependency.py`）
- 代码减少：~200 行（移除样板代码）
- 已注册依赖：9 个

### 验证结果

- ✅ Ruff 检查：全部通过
- ✅ 运行时测试：9 个依赖成功注册
- ✅ CLI 命令：`python -m src.cli.confirm` / `python -m src.cli.dca` 正常运行
- ✅ 无遗留手动依赖注入代码

---

## 2025-11-22 v0.3.1 架构简化与目录重构（阶段 1）

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
