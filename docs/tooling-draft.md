# 工具链配置草案（mypy / ruff）

> 本文档为静态检查工具的**推荐配置草案**，当前阶段仅作参考，暂不强制启用。
> 待代码自然收敛并经过一段时间验证后，再正式落地到 `pyproject.toml` / `mypy.ini` / `ruff.toml`。

---

## 1. mypy 配置草案

### 基础规则（全局）

```ini
[mypy]
python_version = 3.10
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = False  # 初期放宽，后续收紧
disallow_incomplete_defs = True
no_implicit_optional = True
warn_redundant_casts = True
warn_unused_ignores = True
warn_no_return = True
strict_equality = True
```

### 核心层收紧规则

对 `src/core/` 和 `src/usecases/` 应用更严格的类型检查：

```ini
[mypy-src.core.*]
disallow_untyped_defs = True
disallow_any_unimported = True
disallow_any_expr = False  # 暂不启用，避免过度严格
check_untyped_defs = True

[mypy-src.usecases.*]
disallow_untyped_defs = True
check_untyped_defs = True
```

### 第三方库例外

对于缺少类型标注的第三方库，可选择性忽略：

```ini
[mypy-httpx.*]
ignore_missing_imports = True

[mypy-some_other_lib.*]
ignore_missing_imports = True
```

---

## 2. ruff 配置草案

### 基础配置（pyproject.toml）

```toml
[tool.ruff]
line-length = 120
target-version = "py310"

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort (import order)
    "N",    # pep8-naming
    "UP",   # pyupgrade (modernize syntax)
    "B",    # flake8-bugbear (common pitfalls)
    "C4",   # flake8-comprehensions
    "SIM",  # flake8-simplify
    "RET",  # flake8-return (simplify return statements)
    "ARG",  # flake8-unused-arguments
]

ignore = [
    "E501",    # line-too-long (handled by formatter)
    "B008",    # do not perform function calls in argument defaults (FastAPI 常用模式)
    "RET504",  # unnecessary variable assignment before return (有时为可读性保留中间变量)
]

[tool.ruff.lint.per-file-ignores]
"scripts/*.py" = ["T201"]  # 允许脚本中使用 print
"src/jobs/*.py" = ["T201"]  # 允许 job 脚本中使用 print
"src/adapters/notify/*.py" = ["T201"]  # 允许日志适配器使用 print
"src/adapters/datasources/*.py" = ["T201"]  # 允许数据源适配器使用 print

[tool.ruff.lint.isort]
known-first-party = ["src"]
section-order = ["future", "standard-library", "third-party", "first-party", "local-folder"]
```

---

## 3. 推荐的启用顺序

### 第一阶段：基础检查（当前可尝试）

1. **Import 顺序与未使用导入**：
   ```bash
   ruff check --select I,F401 .
   ```

2. **明显的语法问题**：
   ```bash
   ruff check --select F,E9 .
   ```

### 第二阶段：类型检查（代码稳定后）

1. **仅检查核心层**：
   ```bash
   mypy src/core src/usecases
   ```

2. **逐步扩大范围**：
   ```bash
   mypy src/core src/usecases src/adapters
   ```

### 第三阶段：全量静态检查（CI 集成）

在 CI 流程中加入：

```yaml
# .github/workflows/lint.yml (示例)
- name: Run ruff
  run: ruff check .

- name: Run mypy
  run: mypy src
```

---

## 4. 本地开发建议

### VSCode 配置（.vscode/settings.json）

```json
{
  "python.linting.enabled": true,
  "python.linting.mypyEnabled": true,
  "python.linting.mypyArgs": [
    "--config-file=mypy.ini"
  ],
  "python.formatting.provider": "black",
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports": true
  }
}
```

### 预提交钩子（可选）

使用 `pre-commit` 框架自动运行检查：

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.0
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.7.0
    hooks:
      - id: mypy
        additional_dependencies: [types-all]
```

---

## 5. 何时正式启用？

建议在以下条件满足后再正式落地配置文件：

1. **代码稳定期**：完成一轮重构并通过自测验证
2. **无大量告警**：试运行 mypy/ruff 后，告警数量可控（< 50 条）
3. **团队共识**：明确静态检查的价值与约束

---

## 6. 参考链接

- [mypy 官方文档](https://mypy.readthedocs.io/)
- [ruff 官方文档](https://docs.astral.sh/ruff/)
- [Python Type Hints PEP](https://peps.python.org/pep-0484/)
