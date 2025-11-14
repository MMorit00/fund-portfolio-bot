# Coding Log（功能/架构决策）

## 2025-11-14 项目骨架

### 完成内容
- 生成文档骨架与目录结构（core/usecases/adapters/app/jobs）
- 确认命名与分层约定：路径表达领域，文件名简短；依赖通过 Protocol 注入
- 放弃：AI/NLU、历史导入、盘中估值（均不在 MVP 范围）

### 决策
- 使用每日官方净值作为唯一口径；报告/再平衡基于日级数据
- 错误处理：核心抛异常；入口捕获并打印
- 日志：MVP 不引 logging；使用 `app/log.py` 封装 `print`

## 2025-11-14 重构-函数命名优化

### 完成内容
- 重命名 `calc_deviation` → `calc_weight_difference`，消除命名歧义
- 优化 docstring，明确函数计算权重差值（实际-目标）的用途
- 更新相关导入：`src/usecases/portfolio/daily_report.py`

### 决策
- 采用 `weight_difference` 而非 `deviation`，强调返回值是差值而非比例
- 在 docstring 中明确正值=超配、负值=低配的业务含义

### 后续优化
- 优化 `suggest_rebalance_amount` 函数的参数命名和文档
- 重命名参数 `deviation` → `weight_diff`，消除类型语义歧义
- 详细说明输入（权重差值[0,1]小数）与输出（建议金额）的转换逻辑

