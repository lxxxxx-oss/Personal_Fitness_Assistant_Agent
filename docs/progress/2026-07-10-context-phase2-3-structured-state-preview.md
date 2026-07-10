# 2026-07-10 Context Phase 2-3：结构化状态与工具 preview

## 操作类型

功能增强 / Context Compression 前置能力 / 测试补充 / 文档同步

## 变更概述

按照 `docs/optimization/IMPLEMENTATION_SEQUENCE.md` 的第三步，完成 Context Phase 2-3 的最小闭环。

本次新增的是当前会话工作态，不是长期记忆系统：

- 新增 `app/graph/structured_state.py`
- `RouterState` 增加 `_structured_state`
- Router 写入：
  - `task`
  - `decisions`
- Diet 写入：
  - `profile`
  - `knowledge_sources`
- Chat 写入：
  - `knowledge_sources`
- Search 写入：
  - `tool_results_summary`
  - 搜索 prompt 只注入截断后的搜索摘要
  - 完整搜索结果继续保留在 `_search_results`
- MCP 写入：
  - `tool_results_summary`
  - 格式化 prompt 只注入截断后的工具 preview
  - 完整工具结果继续保留在 `_tool_result`
- Motion 写入：
  - `tool_results_summary`
  - 姿态分析完整结果继续保留在 `_tool_results`
- 多意图 `collect_route_result_node` 会保留 `_structured_state`，避免第二个子任务丢掉前一个子任务的结构化摘要

## 当前边界

这一步仍然不是完整 Context Compression：

- `_structured_state` 只是当前图运行中的工作态，不写入长期记忆库
- 尚未实现 compact 触发阈值
- 尚未实现 LLM 摘要或兜底结构化提取
- 尚未把 `_structured_state` 展示给前端
- 还没有做全局 prompt 预算分配，只是先让 Search/MCP 的工具结果 preview 不再无限制塞进 prompt

## 影响范围

- `app/graph/structured_state.py`
- `app/graph/state.py`
- `app/graph/router.py`
- `app/graph/subgraphs/chat.py`
- `app/graph/subgraphs/diet.py`
- `app/graph/subgraphs/search.py`
- `app/graph/subgraphs/mcp.py`
- `app/graph/subgraphs/motion.py`
- `tests/test_router.py`
- `tests/test_search_tool.py`

## 验收结果

见 `docs/tests/2026-07-10-context-phase2-3-structured-state-preview.md`。

## 面试口径

可以这样解释：

> `_structured_state` 不是 Memory，它只是当前任务的工作态。我把 Router 决策、用户画像、知识来源和工具结果摘要放进去，目的是让后续多意图链路、prompt 预算和上下文压缩有结构化输入，而不是继续依赖一大段自然语言历史。完整工具结果仍保留在临时字段里，prompt 只注入 preview，避免搜索结果或工具返回过长时把上下文撑爆。

## Next Steps

等待用户确认后再进入下一步：Memory Phase 2-3，长期记忆基础表、CRUD 与最小 Memory Writer。
