# 2026-07-10 Context Phase 1 Prompt Builder 测试

## 测试目标

验证 Prompt Builder 统一入口不会破坏现有 Chat/Diet RAG prompt、API、流式接口和会话持久化行为，并确认 prompt 长度元数据可用。

## 自动化测试

执行命令：

```powershell
pytest tests\test_search_tool.py tests\test_mcp_client.py tests\test_tool_registry.py tests\test_knowledge_registry_integration.py tests\test_rag_context.py tests\test_conversation_store.py tests\test_api.py tests\test_integration.py tests\test_sliding_window.py -q
```

结果：

```text
80 passed, 1 warning
```

warning 来自 Starlette TestClient/httpx 兼容层弃用提示，与本次 Prompt Builder 重构无关。

## 覆盖内容

- Chat streaming 模式仍能生成 RAG evidence prompt
- Diet streaming 模式仍能生成营养 RAG evidence prompt
- RAG source 透传不受影响
- `PromptBuilder` 会写入 `_prompt_meta.kind`
- `PromptBuilder` 会写入 `_prompt_meta.chars`
- `PromptBuilder` 会写入 `_prompt_meta.sections`
- `/chat`、SSE、WebSocket 和会话持久化相关回归仍通过
- Search、MCP、ToolRegistry 与 Knowledge Registry 相关回归仍通过

## 遗留风险

- 当前测试只验证 Chat/Diet 的 prompt 元数据，因为它们是 Knowledge 主链路中最关键的 RAG prompt。
- Search/MCP 已迁移到 `PromptBuilder`，但本轮没有额外新增专门的 prompt 字符级快照测试，避免测试过度绑定中文模板细节。
- 自动压缩、工具结果 preview 和结构化状态尚未实现，后续阶段需要继续补专项测试。
