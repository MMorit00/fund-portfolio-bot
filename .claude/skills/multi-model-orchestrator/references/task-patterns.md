# 任务模式参考

仅供参考，你自主决定实际组合方式。

---

## 模式速查

| 任务类型 | 建议组合 | 说明 |
|---------|---------|------|
| 架构分析 | gemini | 大范围扫描 |
| 功能流程梳理 | gemini | 追踪调用链 |
| 依赖关系分析 | gemini | 模块间关系 |
| 算法复杂度分析 | codex | 深度推理 |
| 并发安全验证 | codex | 竞态分析 |
| 方案评估 | codex | 利弊权衡 |
| 性能瓶颈定位 | gemini ∥ codex | 并行：扫描 + 推理 |
| Bug 根因分析 | gemini → codex | 串行：定位 → 验证 |
| 重构设计 | gemini → codex | 串行：全貌 → 思路 |
| 代码审查 | gemini ∥ codex | 并行：结构 + 逻辑 |
| 简单修改 | 你直接做 | 无需外部辅助 |

---

## 关键原则

```
gemini/codex 输出 → 分析和建议
代码修改        → 永远由你执行
```

---

## 符号说明

| 符号 | 含义 |
|-----|------|
| `→` | 串行（前者输出供后者参考） |
| `∥` | 并行（同时执行） |

---

## 复杂度判断

| 复杂度 | 特征 | 建议 |
|-------|------|------|
| 简单 | 1-2 文件、明确修改点 | 直接做 |
| 中等 | 3-4 文件、有逻辑关联 | 单 agent 辅助 |
| 复杂 | 5+ 文件、算法/架构 | 多 agent 协作 |

---

## PAL MCP Server 配置速查

### 模型切换

```bash
# Gemini 常用模型
gemini-2.5-pro          # 高性能推理
gemini-2.5-flash        # 快速响应
gemini-3-flash-preview  # 最新预览

# 切换命令
./scripts/switch-model.sh gemini gemini-2.5-pro
```

### 配置位置

| 项目 | 路径 |
|-----|------|
| CLI 配置 | `pal-mcp-server/conf/cli_clients/*.json` |
| 系统提示词 | `pal-mcp-server/systemprompts/clink/*.txt` |
| 用户覆盖 | `~/.pal/cli_clients/*.json` |

### 输出限制

- clink 最大响应：50,000 字符
- 超限时自动提取 `<SUMMARY>` 标签内容
- 无 SUMMARY 则截断并显示前 25,000 字符摘录
