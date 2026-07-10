# 2026-07-10 Memory Phase 6 Milvus 用户记忆测试

## 测试目标

验证用户长期记忆 Milvus 同步任务的最小闭环：正式 memory 生成 embedding job，worker 可处理成功或失败，语义检索结果可与 SQLite 检索结果合并，Milvus 失败时主链路仍可用。

## 自动化测试

执行命令：

```powershell
pytest tests\test_memory_store.py tests\test_conversation_store.py tests\test_api.py tests\test_integration.py tests\test_sliding_window.py tests\test_search_tool.py tests\test_mcp_client.py tests\test_tool_registry.py tests\test_knowledge_registry_integration.py tests\test_rag_context.py tests\test_router.py tests\test_milvus_retriever.py tests\test_config.py -q
```

结果：

```text
135 passed, 1 warning
```

warning 来自 Starlette TestClient/httpx 兼容层弃用提示，与本次 Milvus 用户记忆增强无关。

## 覆盖内容

- 启用 semantic memory 后，正式记忆创建会生成 pending embedding job
- `process_embedding_jobs` 成功时 job 变为 completed
- fake semantic retriever 可返回 memory_id 作为 source，并合并进搜索结果
- semantic retriever 失败时 job 变为 failed
- semantic 失败后 SQLite FTS5/LIKE 仍可召回
- `/memory/embedding-jobs` 和 `/memory/embedding-jobs/process` API 可用
- 既有 Milvus RAG retriever 合同测试、API、Router、ToolRegistry、RAG、Context、会话持久化回归通过

## 遗留风险

- 当前没有启动真实 Milvus 服务执行用户记忆 Collection 的真实集成测试。
- 当前是同步处理接口，不是常驻后台 worker。
- 当前删除 memory 后依靠 SQLite active 状态过滤，不主动删除 Milvus 派生向量。
