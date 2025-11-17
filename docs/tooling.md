# 工具链配置（ruff / mypy）

> 本文档记录项目的静态检查工具配置。
> - **ruff 基础配置**：已落地到 `pyproject.toml`，日常使用。
> - **mypy**：仅在排查复杂类型问题时按需使用，不强制启用。

---

## 1. ruff 配置（已落地）

### 当前配置（pyproject.toml）

```toml
[tool.ruff]
line-length = 120
target-version = "py310"

[tool.ruff.lint]
select = ["F", "E", "I"]  # pyflakes + 基础错误 + import 排序
ignore = ["E501"]         # 行长度交给格式化工具处理

[tool.ruff.lint.per-file-ignores]
"scripts/*.py" = ["T201"]
"src/jobs/*.py" = ["T201"]
"src/adapters/notify/*.py" = ["T201"]
"src/adapters/datasources/*.py" = ["T201"]

[tool.ruff.lint.isort]
known-first-party = ["src"]
```

### 启用的规则说明

- **F（pyflakes）**：检测未使用的导入、变量等
- **E（pycodestyle errors）**：基础语法错误
- **I（isort）**：自动整理 import 顺序

### 日常使用

```bash
# 检查所有问题
ruff check .

# 自动修复可修复的问题
ruff check --fix .
```

### 长行处理策略

对于 SQL 字符串、中文提示等合理的长行，使用 `# noqa: E501` 忽略：

```python
# ✅ 合理使用 noqa
lines.append(
    f"提示：今日 {count} 只基金有有效 NAV，总市值可能低估。\n"  # noqa: E501
)
```

---

## 2. mypy 使用建议（按需启用）

mypy 适合在**排查复杂类型问题**时使用，不建议全局强制启用。

### 按需检查

```bash
# 安装
uv add --dev mypy

# 检查单个文件（推荐）
mypy src/usecases/portfolio/daily_report.py

# 检查核心模块
mypy src/core src/usecases
```

### 最小配置建议

如需配置文件，创建 `mypy.ini`（可选）：

```ini
[mypy]
python_version = 3.10
warn_unused_configs = True
disallow_incomplete_defs = True
no_implicit_optional = True

# 第三方库忽略
[mypy-httpx.*]
ignore_missing_imports = True
```

---

## 3. 不推荐的配置（仅作参考）

以下配置适合大型团队项目，个人项目**不建议启用**，会增加开发负担。

### pre-commit 钩子

```yaml
# .pre-commit-config.yaml（不推荐）
# 个人项目手动运行 ruff check 即可，无需强制钩子
```

### 严格 mypy 配置

```ini
# mypy.ini（不推荐）
[mypy]
strict = True  # 过于严格，个人项目不需要
```

### ruff 高级规则

```toml
# pyproject.toml（不推荐）
select = ["SIM", "C4", "UP", "B", "RET", "ARG"]  # 会产生大量非关键告警
```

---

## 4. 参考链接

- [ruff 官方文档](https://docs.astral.sh/ruff/)
- [mypy 官方文档](https://mypy.readthedocs.io/)
- [Python Type Hints PEP](https://peps.python.org/pep-0484/)
