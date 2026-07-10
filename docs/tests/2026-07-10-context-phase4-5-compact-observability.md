# 2026-07-10 Context Phase 4-5 compact 测试

## 测试目标

验证长 prompt 超过阈值后会触发确定性 compact，并确认 compact 后 prompt 不超过最大长度，同时保留可观测元数据和执行轨迹。

## 自动化测试

执行命令：

```powershell
pytest tests\test_memory_store.py tests\test_conversation_store.py tests\test_api.py tests\test_integration.py tests\test_sliding_window.py tests\test_search_tool.py tests\test_mcp_client.py tests\test_tool_registry.py tests\test_knowledge_registry_integration.py tests\test_rag_context.py tests\test_router.py -q
```

结果：

```text
123 passed, 1 warning
```

warning 来自 Starlette TestClient/httpx 兼容层弃用提示，与本次 compact 实现无关。

## 覆盖内容

- prompt 超过 `COMPACT_TRIGGER_CHARS` 后触发 compact
- compact 后 prompt 不超过 `MAX_PROMPT_CHARS`
- `_prompt_meta.compact_triggered` 为 true
- `_prompt_meta.original_chars` 记录压缩前长度
- `_structured_state.compact_summary` 记录结构化摘要
- `_execution` 中出现 `component=compact`
- 既有 Memory、API、Router、ToolRegistry、RAG、会话持久化回归通过

## 遗留风险

- 当前没有 LLM 摘要。
- 当前 compact summary 尚未持久化到 `summaries` 表。
- 当前没有前端展示 compact 状态。
