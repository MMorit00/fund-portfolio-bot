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

