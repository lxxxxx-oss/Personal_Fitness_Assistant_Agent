# Progress 最近记录

`docs/progress/` 保存日期化实现、修复和文档调整记录。本页只索引最近 10 条，避免导航继续膨胀；未列出的旧文件作为历史证据保留。当前项目状态仍以 [../README.md](../README.md) 为准，测试证据看 [../tests/README.md](../tests/README.md)。

保留规则：

- 索引按日期倒序展示最近 10 条；同一天按文件名倒序确定顺序。
- 新增记录时从索引移除最旧条目，但不要求删除历史文件。
- 长期有效的设计结论沉淀到 `technical/`，接口和运行事实沉淀到 `API.md`、`README.md` 或 `RUNBOOK.md`。
- progress 是近期过程记录，不承担长期档案库职责。

## 最近 10 条

| 日期 | 记录 | 重点 |
|---|---|---|
| 2026-07-02 | [小程序阶段 1：回答元数据闭环](./2026-07-02-miniprogram-result-contract.md) | 三种对话协议统一透传 sources/warnings，小程序增加来源与运行提示卡片 |
| 2026-07-01/02 | [Milvus RAG 接入与验证记录](./2026-07-01-milvus-rag-wip.md) | Retriever、索引、内存降级和 Compose 已加入；SDK 与容器健康已确认，真实 CRUD 冒烟仍待完成 |
| 2026-06-30 | [Interview 简历口径修正](./2026-06-30-interview-resume-alignment-fix.md) | 移除默认看代码假设，按简历主线重写 P0/P1/P2 面试材料 |
| 2026-06-30 | [简历口径优先规则](./2026-06-30-resume-first-interview-rule.md) | 忽略本地简历 JSON，interview 材料围绕简历项目描述组织 |
| 2026-06-30 | [面试回答风格再梳理](./2026-06-30-interview-answer-style-refinement.md) | 从标准答案改为项目思路、技术取舍、问题解决和边界说明 |
| 2026-06-30 | [Router Phase 4 实施](./2026-06-30-router-phase4-implementation.md) | 多意图识别、白名单组合执行、错误隔离和结果合成 |
| 2026-06-30 | [MCP 菜谱退出核心架构（已被后续口径取代）](./2026-06-30-mcp-core-scope-reduction-decision.md) | 保留当时的范围收敛记录；当前路线继续保留 MCP 工具适配层 |
| 2026-06-30 | [面试学习材料重组](./2026-06-30-interview-study-material-reorganization.md) | `interview/` 收敛为 P0/P1/P2 分级材料 |
| 2026-06-30 | [面试与运行边界](./2026-06-30-interview-runtime-boundary.md) | 明确已实现、当前边界和后续规划的表达原则 |
| 2026-06-30 | [面试准备审查](./2026-06-30-interview-preparation-audit.md) | 面试资料事实审查和优化清单 |

## 维护方式

新增记录必须写清：变更概述、影响范围、验证结果、遗留问题和下一步。记录完成后，同时检查：

- 是否需要更新 `docs/README.md` 的当前状态。
- 是否改变 `docs/API.md` 的接口事实。
- 是否改变 `docs/RUNBOOK.md` 的运行方式。
- 是否需要在 `docs/tests/` 增加验收记录。
