# Progress 最近记录

`docs/progress/` 只保留最近 10 条日期化记录，用于快速追溯近期实现、修复和文档调整。当前项目状态仍以 [../README.md](../README.md) 为准，测试证据看 [../tests/README.md](../tests/README.md)。

保留规则：

- 按文件名中的日期倒序保留最近 10 条；同一天按文件名倒序确定顺序。
- 新增第 11 条记录时，删除最旧一条，并同步更新本页。
- 长期有效的设计结论沉淀到 `technical/`，接口和运行事实沉淀到 `API.md`、`README.md` 或 `RUNBOOK.md`。
- progress 是近期过程记录，不承担长期档案库职责。

## 最近 10 条

| 日期 | 记录 | 重点 |
|---|---|---|
| 2026-07-01 | [Milvus RAG 接入（WIP）](./2026-07-01-milvus-rag-wip.md) | Milvus Retriever、IVF_FLAT/COSINE、内存降级和 Compose 已加入；真实服务联调与全量回归待完成 |
| 2026-06-30 | [Interview 简历口径修正](./2026-06-30-interview-resume-alignment-fix.md) | 移除默认看代码假设，按简历主线重写 P0/P1/P2 面试材料 |
| 2026-06-30 | [简历口径优先规则](./2026-06-30-resume-first-interview-rule.md) | 忽略本地简历 JSON，interview 材料围绕简历项目描述组织 |
| 2026-06-30 | [面试回答风格再梳理](./2026-06-30-interview-answer-style-refinement.md) | 从标准答案改为项目思路、技术取舍、问题解决和边界说明 |
| 2026-06-30 | [Router Phase 4 实施](./2026-06-30-router-phase4-implementation.md) | 多意图识别、白名单组合执行、错误隔离和结果合成 |
| 2026-06-30 | [MCP 菜谱退出核心架构（已被后续口径取代）](./2026-06-30-mcp-core-scope-reduction-decision.md) | 保留当时的范围收敛记录；当前路线继续保留 MCP 工具适配层 |
| 2026-06-30 | [面试学习材料重组](./2026-06-30-interview-study-material-reorganization.md) | `interview/` 收敛为 P0/P1/P2 分级材料 |
| 2026-06-30 | [面试与运行边界](./2026-06-30-interview-runtime-boundary.md) | 明确已实现、当前边界和后续规划的表达原则 |
| 2026-06-30 | [面试准备审查](./2026-06-30-interview-preparation-audit.md) | 面试资料事实审查和优化清单 |
| 2026-06-30 | [P0 面试主线可读性优化](./2026-06-30-interview-p0-readability-optimization.md) | 通俗比喻、口语化主线、分轮学习和自测标准 |

## 维护方式

新增记录必须写清：变更概述、影响范围、验证结果、遗留问题和下一步。记录完成后，同时检查：

- 是否需要更新 `docs/README.md` 的当前状态。
- 是否改变 `docs/API.md` 的接口事实。
- 是否改变 `docs/RUNBOOK.md` 的运行方式。
- 是否需要在 `docs/tests/` 增加验收记录。
