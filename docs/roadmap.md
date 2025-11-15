# Roadmap（版本规划 & 大 TODO）

## v0.1（当前 MVP）
- [ ] 基金 & 资产类别管理（FundRepo / AllocConfig）
- [ ] 交易记录：`/buy` `/sell`（CreateTrade）
- [ ] 定投计划：生成 pending 与跳过（RunDailyDca / SkipDcaForDate）
- [ ] 官方净值抓取（NavProvider + NavRepo）
- [ ] T+1/T+2 确认（ConfirmPendingTrades）
- [ ] 日报（GenerateDailyReport + Discord Webhook）

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
  - 方案备选：在适配层引入 SQLAlchemy Core 或轻量 Query Builder
  - 目标：减少硬编码 SQL 和重复 `_row_to_xxx`，提升可维护性与类型安全