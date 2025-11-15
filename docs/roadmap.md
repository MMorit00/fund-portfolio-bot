# Roadmap（版本规划 & 大 TODO）

## v0.1（当前 MVP）
- [x] 基金 & 资产类别管理（FundRepo / AllocConfig）
- [x] 交易记录：`/buy` `/sell`（CreateTrade）—— CLI 已完成
- [x] 定投计划：生成 pending 与跳过（RunDailyDca / SkipDcaForDate）—— RunDailyDca 已完成并装配
- [x] 官方净值抓取（NavProvider + NavRepo）—— 本地 NavProvider 已完成（方案 A）
- [x] T+1/T+2 确认（ConfirmPendingTrades）—— 已完成并装配
- [ ] 日报（GenerateDailyReport + Discord Webhook）—— 骨架已完成，内容待实现

## v0.2（计划）
- [ ] 周报 / 月报（基础版）
- [ ] 再平衡建议（文字提示 + 建议区间）
- [ ] 冷却期机制配置化

## v0.3（未来方向）
- [ ] 历史导入（严格 CSV 模板）
- [ ] 盘中估值作为附加信息（不作为核心口径）
- [ ] 自然语言 AI 接口（基于现有 UseCases）




## 技术债 / 重构

- [ ] 评估在 `adapters/db/sqlite` 层替换手写 SQL
  - 保持 `core` / `usecases` 只依赖领域模型，不直接依赖 ORM
  - 方案备选：在适配层引入 SQLAlchemy Core 或 轻量 Query Builder
  - 目标：减少硬编码 SQL 和重复 `_row_to_xxx`，提升可维护性与类型安全

- [ ] **[重要] 修复 T+1/T+2 确认规则的不确定性**
  - **问题**：当前 `get_confirm_date()` 过于简化，无法处理真实业务复杂情况
  - **影响**：交易确认可能不准确，影响持仓计算和日报生成
  - **改进方向**：
    - 引入交易日历表，支持节假日规则
    - 实现动态确认策略，考虑基金特性、交易时间
    - 添加确认重试机制，处理净值数据缺失
    - 完善基金模型，支持不同基金类型的确认规则

- [ ] **[重要] 日报计算精度问题**
  - **问题**：当前 `GenerateDailyReport` 基于份额计算权重，不是基于市值
  - **影响**：配置偏离分析不准确，再平衡建议可能错误
  - **改进方向**：
    - 集成实时净值数据进行市值计算
    - 缓存市值计算结果提升性能
    - 提供份额视图和市值视图两种模式