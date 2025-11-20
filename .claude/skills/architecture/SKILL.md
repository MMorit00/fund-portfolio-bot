---
name: architecture
description: Enforces the domain-driven layering and dependency rules for the fund-portfolio-bot project, keeping core, usecases, adapters, and app correctly separated. Use when designing new components, changing imports, or reviewing architecture decisions in this repository.
---

# Architecture and layering for fund-portfolio-bot

本 Skill 关注分层职责与依赖方向。详细说明参见 `docs/architecture.md`。

## 层次结构概览

项目采用自外向内依赖的分层架构：

- `core/`：领域模型、实体、值对象、领域服务、业务规则
- `usecases/`：应用服务与用例，编排领域逻辑
- `adapters/`：对外适配层，例如数据库、CLI、HTTP、调度器等
- `app/`：组装根（composition root），负责配置与依赖注入

## 依赖规则（必须遵守）

依赖方向：**只能向内依赖**：

- `core/`
  - 只能依赖 `core/` 内部其他模块
  - 不得导入 `usecases/`、`adapters/`、`app/`
- `usecases/`
  - 可以依赖 `core/`
  - 可以依赖抽象端口 / 协议（Protocol）
- `adapters/`
  - 可以依赖 `core/` 与 `usecases/`
  - 可以依赖需要实现的端口 / 协议接口
- `app/`
  - 可以依赖上述所有层，用来完成具体装配

额外约束：

- 共享的端口 / 协议接口应集中定义在统一位置，例如
  `src/core/protocols.py`（或项目中约定的 protocols 模块）。
- 避免任何形式的循环导入，如发现，优先通过抽象接口或拆分模块解决。

## 设计或修改代码时的步骤

1. **识别所在层级**

   - 判断当前文件属于 `core` / `usecases` / `adapters` / `app` 中的哪一层。
   - 确保其职责与该层定位一致：
     - 业务规则 → `core`
     - 用例编排 → `usecases`
     - IO / 持久化 / 接口适配 → `adapters`
     - 组合与配置 → `app`

2. **检查 import 是否合规**

   在添加或修改 import 之前：

   - 确认引用目标所在层级是"允许依赖的内层"。
   - 在需要依赖外层实现时，优先依赖抽象 Protocol，而不是具体适配器类。

3. **扩展新功能时的推荐路径**

   - 先在 `core/` 中补充必要的领域概念（实体、值对象、领域服务）。
   - 再在 `usecases/` 中编排业务流程。
   - 在 `adapters/` 中实现持久化、消息队列、CLI、HTTP 等具体适配。
   - 最后在 `app/` 中完成具体装配与配置注册。

## Review checklist

在做架构 / 分层相关 Review 时，可以逐条检查：

- [ ] `core/` 内没有从 `adapters/` 或 `app/` 导入。
- [ ] 用例层依赖的是领域模型和端口接口，而不是具体适配器实现。
- [ ] 新增的 Protocol 放在统一的协议模块中，而不是分散在各个层。
- [ ] 没有引入新的循环依赖链。
- [ ] 代码的控制流与数据流仍然符合 `docs/architecture.md` 中描述的结构。
