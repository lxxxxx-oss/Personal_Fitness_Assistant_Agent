# 2026-07-09 Knowledge ToolRegistry Integration Test

## Test Object

Knowledge/RAG retrieval through the minimal `ToolRegistry`.

## What Was Tested

- Chat retrieval node calls `knowledge.retrieve` through Registry.
- Diet nutrition retrieval node calls the same Registry-backed Knowledge helper.
- Registry metadata is available in `_retrieval_meta`.
- RAG execution trace remains compatible.
- Registry-backed retrieval failure degrades cleanly.
- Full project regression remains green.

## Commands

```powershell
pytest tests\test_knowledge_registry_integration.py tests\test_tool_registry.py tests\test_rag_context.py -q
pytest tests\test_search_tool.py tests\test_diet_profile.py tests\test_integration.py tests\test_router.py -q
pytest -q
```

## Results

- `17 passed`
- `51 passed, 1 warning`
- Full regression: `170 passed, 2 skipped, 1 warning`

## Conclusion

Knowledge/RAG is now governed by the same minimal registry as Search. The project can defensibly say both external real-time search and local knowledge retrieval use the internal tool governance layer.

## Remaining Risk

- Motion and MCP are not yet migrated.
- Registry timeout is not hard cancellation.
- Registry audit data is still in-memory.
