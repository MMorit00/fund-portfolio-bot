# Python 代码规范（MVP）

目标：简洁、可读、稳定，便于后续扩展。

- 类型注解：全部启用（函数参数/返回值/主要字段）。
- Docstring：中文，说明职责/输入/输出/注意事项。
- 金额/净值/份额：使用 `decimal.Decimal`，禁止 float 参与金融计算。
- 舍入与保留：金额 2 位、净值 4 位、份额 4 位（可配置，保持一致）。
- 文件命名：snake_case；路径表达语义，文件名尽量简短。
- 导入顺序：标准库 → 第三方 → 项目内部。
- 目录职责：
  - `core` 仅含纯领域逻辑，不依赖外部库实现
  - `usecases` 仅依赖 `core` 与 `ports`（Protocol）
  - `adapters` 实现具体技术，供 `app/wiring` 装配
  - `jobs` 仅做参数解析与调用 usecase，不写业务
- 错误处理：核心抛异常；入口捕获并 `print`。
- 日志：使用 `app/log.py` 的 `log()`；不引 logging 框架。
- SQL 打印：通过 SQLite trace 回调；可用 `ENABLE_SQL_DEBUG` 控制。

