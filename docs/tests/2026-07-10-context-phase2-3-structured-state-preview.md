# 2026-07-10 Context Phase 2-3 结构化状态与工具 preview 测试

## 测试目标

验证 `_structured_state` 能记录 Router 决策、工具摘要和多意图链路中的跨步骤工作态，同时确认 API、RAG、ToolRegistry、MCP、Search 和会话持久化回归不受影响。

## 自动化测试

执行命令：

```powershell
pytest tests\test_search_tool.py tests\test_mcp_client.py tests\test_tool_registry.py tests\test_knowledge_registry_integration.py tests\test_rag_context.py tests\test_router.py tests\test_conversation_store.py tests\test_api.py tests\test_integration.py tests\test_sliding_window.py -q
```

结果：

```text
114 passed, 1 warning
```

warning 来自 Starlette TestClient/httpx 兼容层弃用提示，与本次结构化状态和工具 preview 改造无关。

## 覆盖内容

- Router 会写入 `_structured_state.task`
- Router 会写入 `_structured_state.decisions`
- 多意图组合执行时，`collect_route_result_node` 不会清空 `_structured_state`
- Search 工具执行后会写入 `_structured_state.tool_results_summary`
- Search 完整结果仍保留在 `_search_results`
- ToolRegistry、MCP、Knowledge Registry、RAG source 透传、API、会话持久化和 SlidingWindow 回归通过

## 遗留风险

- 当前没有把 `_structured_state` 暴露到 API 响应或前端 UI。
- 当前只做工具结果 preview 截断，没有做全局 token 预算分配。
- Motion preview 已写入结构化状态，但本轮没有新增真实媒体专项测试，仍依赖既有 Motion 专项验收记录。
