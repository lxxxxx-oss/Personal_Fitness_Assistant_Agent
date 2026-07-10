# 2026-07-10 Memory Phase 2-3 长期记忆测试

## 测试目标

验证长期记忆基础表、CRUD 接口、逻辑删除、显式 Memory Writer 和去重逻辑可用，同时确认聊天、Router、ToolRegistry、RAG、Context 前置能力和会话持久化回归不受影响。

## 自动化测试

执行命令：

```powershell
pytest tests\test_memory_store.py tests\test_conversation_store.py tests\test_api.py tests\test_integration.py tests\test_sliding_window.py tests\test_search_tool.py tests\test_mcp_client.py tests\test_tool_registry.py tests\test_knowledge_registry_integration.py tests\test_rag_context.py tests\test_router.py -q
```

结果：

```text
119 passed, 1 warning
```

warning 来自 Starlette TestClient/httpx 兼容层弃用提示，与本次长期记忆实现无关。

## 覆盖内容

- `MemoryStore` 可创建长期记忆
- `MemoryStore` 可列表、读取、更新和逻辑删除长期记忆
- 删除后的记忆默认不出现在列表中
- `include_deleted=true` 可查看已删除记忆
- 显式“请记住……”可以写入长期记忆
- 重复显式记忆会通过 `memory_key` 去重
- `/memory` CRUD 接口可用
- `/chat` 中显式“请记住……”会触发最小 Memory Writer
- 既有 API、Router、ToolRegistry、RAG、Context、会话持久化回归通过

## 遗留风险

- 当前没有候选确认流，隐私/健康信息仍不应通过自动推断写入。
- 当前长期记忆还没有进入 Prompt Builder，因此不会影响回答个性化。
- 当前没有 FTS5/Milvus 用户记忆检索，`memory_items` 只是 SQLite source of truth。
