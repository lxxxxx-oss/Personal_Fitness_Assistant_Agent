# Progress 最近记录

`docs/progress/` 保存日期化实现、修复和文档调整记录。本页只索引最近 10 条，避免导航继续膨胀；未列出的旧文件作为历史证据保留。当前项目状态仍以 [../README.md](../README.md) 为准，测试证据看 [../tests/README.md](../tests/README.md)。

保留规则：

- 索引按完成时间倒序展示最近 10 条；同一天按实际完成顺序排列。
- 新增记录时从索引移除最旧条目，但不要求删除历史文件。
- 长期有效的设计结论沉淀到 `technical/`，接口和运行事实沉淀到 `API.md`、`README.md` 或 `RUNBOOK.md`。
- progress 是近期过程记录，不承担长期档案库职责。

## 最近 10 条

| 日期 | 记录 | 重点 |
|---|---|---|
| 2026-07-10 | [Context Phase 4-5：compact 触发与可观测性](./2026-07-10-context-phase4-5-compact-observability.md) | PromptBuilder 统一触发确定性 compact，记录 `_prompt_meta` 与 `execution` compact 轨迹 |
| 2026-07-10 | [Memory Phase 4-5：候选确认、FTS5 检索与预算注入](./2026-07-10-memory-phase4-5-candidates-fts-injection.md) | 敏感记忆先进 candidate，确认后入库；长期记忆 FTS5/LIKE 检索并注入 Knowledge prompt |
| 2026-07-10 | [Memory Phase 2-3：长期记忆 CRUD 与最小 Memory Writer](./2026-07-10-memory-phase2-3-long-term-memory-writer.md) | SQLite 新增 `memory_items/sources/relations`，`/memory` CRUD 与显式“记住”写入 |
| 2026-07-10 | [Context Phase 2-3：结构化状态与工具 preview](./2026-07-10-context-phase2-3-structured-state-preview.md) | `_structured_state` 记录任务、决策、画像、知识来源和工具摘要；Search/MCP/Motion 写入 preview |
| 2026-07-10 | [Context Phase 1：Prompt Builder 统一入口](./2026-07-10-context-phase1-prompt-builder.md) | Chat/Diet/Search/MCP 的主要文本 prompt 收束到 `PromptBuilder`，并记录 `_prompt_meta.kind/chars/sections` |
| 2026-07-10 | [Memory Phase 1：会话持久化最小闭环](./2026-07-10-memory-phase1-conversation-persistence.md) | SQLite 落地 conversations/messages/summaries/task_states，`conversation_id` 支持续接会话，SlidingWindowMemory 作为 hot cache |
| 2026-07-09 | [ToolRegistry 阶段总结](./2026-07-09-tool-registry-stage-summary.md) | 收束 Search、Knowledge/RAG、MCP execute 已接入状态，并标记 Motion compare 暂缓 |
| 2026-07-09 | [MCP 接入 ToolRegistry](./2026-07-09-mcp-tool-registry-integration.md) | MCP `execute_tool_node` 通过 `mcp.call_tool` 接入 Registry，并完成全量回归 |
| 2026-07-09 | [Motion/MCP Registry 迁移评估](./2026-07-09-motion-mcp-registry-migration-evaluation.md) | 形成先 MCP execute、后 Motion compare 的顺序；MCP execute 已在后续步骤完成 |
| 2026-07-09 | [Knowledge 接入 ToolRegistry](./2026-07-09-knowledge-tool-registry-integration.md) | Chat/Diet 的 RAG 检索通过 `knowledge.retrieve` 接入 Registry，并完成全量回归 |

## 维护方式

新增记录必须写清：变更概述、影响范围、验证结果、遗留问题和下一步。记录完成后，同时检查：

- 是否需要更新 `docs/README.md` 的当前状态。
- 是否改变 `docs/API.md` 的接口事实。
- 是否改变 `docs/RUNBOOK.md` 的运行方式。
- 是否需要在 `docs/tests/` 增加验收记录。
