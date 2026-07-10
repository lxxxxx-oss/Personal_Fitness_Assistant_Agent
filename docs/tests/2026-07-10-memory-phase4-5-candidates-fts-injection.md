# 2026-07-10 Memory Phase 4-5 候选确认与检索注入测试

## 测试目标

验证敏感候选记忆、确认/拒绝接口、SQLite FTS5/LIKE 检索、访问次数更新和 Prompt Builder 长期记忆注入可用，同时确认前序 API、Router、ToolRegistry、Context 和会话持久化回归不受影响。

## 自动化测试

执行命令：

```powershell
pytest tests\test_memory_store.py tests\test_conversation_store.py tests\test_api.py tests\test_integration.py tests\test_sliding_window.py tests\test_search_tool.py tests\test_mcp_client.py tests\test_tool_registry.py tests\test_knowledge_registry_integration.py tests\test_rag_context.py tests\test_router.py -q
```

结果：

```text
122 passed, 1 warning
```

warning 来自 Starlette TestClient/httpx 兼容层弃用提示，与本次记忆系统增强无关。

## 覆盖内容

- 敏感显式记忆会进入 `candidate_memories`
- pending candidate 默认不会进入正式长期记忆列表
- candidate 确认后会写入 `memory_items`
- `/memory/candidates`、confirm、reject API 可用
- `/memory/search` 可召回正式长期记忆
- 检索后会更新 `access_count`
- Chat prompt 会注入长期记忆段
- 长期记忆 prompt 段受预算限制
- 既有 API、Router、ToolRegistry、RAG、Context、会话持久化回归通过

## 遗留风险

- 还没有前端候选确认入口。
- 还没有 Milvus 用户记忆语义检索。
- 还没有全局 prompt token 预算器和 compact 联动。
