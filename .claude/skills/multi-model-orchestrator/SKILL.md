---
name: multi-model-orchestrator
description: |
  多模型协调器（用于复杂任务和大范围探索）

  **场景 A：复杂代码修改**（需满足至少 2 项）
  - 涉及 3+ 个文件的修改
  - 需要设计新算法或重构核心逻辑
  - 架构级别的决策（分层变更、依赖关系重组）
  - 并发/状态管理等高风险代码

  **场景 B：大范围探索**（替代 Explore agent）
  - 理解跨多个目录的架构和功能流程
  - 探索涉及 5+ 个文件的实现细节
  - 需要深度分析（不是简单查找）
  → 使用 gemini-agent（1M 上下文）进行穷尽式探索

  **不触发**：
  - 简单功能添加/bug 修复（1-2 个文件）
  - 查找特定函数/类定义（用 Grep/Glob）
  - 纯文档更新或 UI 样式调整
---

# 多模型协调器

协调 Gemini（长上下文）和 Codex（强推理）与 Claude（代码质量）的协作。

## 核心原则：质量优先

### 成本策略

```
┌─────────────────────────────────────────────────────────┐
│  Gemini/Codex 输出  →  便宜，让它尽可能多地输出          │
│  haiku 处理         →  便宜，负责去除噪音                │
│  Opus 接收          →  贵，只接收有价值的内容            │
└─────────────────────────────────────────────────────────┘
```

### 过滤原则

```
❌ 错误：过度精简，压缩字数，丢失细节
✅ 正确：去除噪音，保留完整的分析和推理
```

**什么是噪音**（应该移除）：
- clink 返回的 metadata（duration、return_code）
- 模型的寒暄（"好的，我来帮你..."）
- JSON 结构包装

**什么是价值**（必须保留）：
- 完整的分析结论
- **Codex 的推理链条**（比结论更重要）
- 所有发现的问题
- 具体的文件路径、行号、代码示例

## 模型能力矩阵

| 模型 | 优势 | 适用任务 |
|-----|------|---------|
| Gemini | 1M 上下文，解释能力 | 多文件分析、文档、架构理解 |
| Codex | 深度推理 (GPT-5.2) | 逻辑验证、边界分析、方案评估 |
| Claude | 代码质量 | 最终代码编写、综合决策 |

## 任务路由决策

```
任务类型判断
    │
    ├─ 简单/明确 ──→ Claude 直接处理
    │
    ├─ 查找特定函数/类 ──→ Grep/Glob（不触发）
    │
    ├─ 大范围探索（5+ 文件）──→ gemini-agent（替代 Explore）
    │
    ├─ 需要逻辑验证 ──→ codex-agent
    │
    └─ 复杂任务 ──→ 并行调用 + Claude 综合
```

## 工作流模式

### 模式 A：并行分析（复杂任务）

```
         ┌─────────────┐
         │ Claude 解析 │
         └──────┬──────┘
                │
    ┌───────────┼───────────┐
    ↓                       ↓
gemini-agent           codex-agent
(上下文分析)           (逻辑推理)
    ↓                       ↓
    └───────────┬───────────┘
                ↓
         ┌─────────────┐
         │ Claude 综合 │
         │  产出代码   │
         └─────────────┘
```

**触发条件**：
- 涉及多个文件的修改
- 需要设计新的算法/逻辑
- 架构级别的决策

### 模式 B：串行验证（代码产出后）

```
Claude 写代码 → codex-agent 验证 → 通过/修复
```

**触发条件**：
- 关键业务逻辑
- 算法实现
- 并发/状态管理代码

### 模式 C：单模型（简单任务）

```
gemini-agent 解释 → 直接返回
```

**触发条件**：
- 代码解释请求
- 文档总结
- 简单问答

### 模式 D：探索模式（替代 Explore agent）

```
gemini-agent 深度探索 → 返回完整分析
```

**触发条件**：
- 理解跨多个目录的功能流程
- 探索涉及 5+ 个文件的实现
- 需要深度分析，不是简单查找

**特点**：
- 利用 Gemini 的 1M 上下文容量
- 使用探索专用 prompt 模板（见 `references/gemini-prompts.md`）
- 要求穷尽式分析，返回尽可能多的细节
- 比 Explore agent 更适合深度理解场景

## 并行调用语法

在一条消息中启动多个 Task：

```
同时调用 gemini-agent 和 codex-agent：

Task 1 (gemini-agent):
- prompt: "分析这些文件的架构..."
- subagent_type: gemini-agent

Task 2 (codex-agent):
- prompt: "评估这个方案的可行性..."
- subagent_type: codex-agent
```

## 结果综合原则

收到子代理结果后：

1. **对比分析**：Gemini 和 Codex 的结论是否一致
2. **冲突处理**：如有分歧，倾向 Codex 的逻辑推理
3. **综合决策**：结合两者优势做最终方案
4. **代码产出**：由 Claude 编写最终代码

## 质量保证

关键代码必须经过 codex-agent 验证：

```
产出代码
    ↓
codex-agent 验证
    ↓
  ┌─┴─┐
  ↓   ↓
 ✓   ✗ → 修复 → 重新验证
```

## 资源文件

### 脚本 (scripts/)

| 脚本 | 用途 | 用法 |
|-----|------|-----|
| `check-cli-health.sh` | 检查 CLI 可用性 | `./scripts/check-cli-health.sh [gemini\|codex\|all]` |
| `extract-content.py` | 从 clink 响应提取内容 | `echo '{...}' \| python scripts/extract-content.py` |

**健康检查**：调用外部模型前，先确认 CLI 可用：
```bash
./scripts/check-cli-health.sh all
# 输出: gemini:available, codex:available, status:all_available
```

### 参考文档 (references/)

| 文件 | 内容 |
|-----|------|
| `task-patterns.md` | 任务类型 → 模型组合的完整映射表 |
| `prompt-templates.md` | Prompt 模板库索引（导航到具体模板文件）|
| `gemini-prompts.md` | Gemini 专用 prompt 模板 |
| `codex-prompts.md` | Codex 专用 prompt 模板 |

**使用 Prompt 模板**：
- 代码分析/探索 → 见 `gemini-prompts.md`
- 逻辑验证/推理 → 见 `codex-prompts.md`
