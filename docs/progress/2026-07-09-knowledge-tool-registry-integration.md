# 2026-07-09 Knowledge ToolRegistry Integration

## Type

Feature integration.

## Background

After Search was routed through `ToolRegistry`, the next low-risk and high-interview-value step was Knowledge/RAG. This proves the registry can govern both external real-time search and local knowledge retrieval.

## Changes

- Added shared Knowledge retrieval helper in `app/graph/subgraphs/rag_context.py`.
- Routed Chat RAG retrieval through `ToolRegistry.execute("knowledge.retrieve", ...)`.
- Routed Diet nutrition retrieval through the same registry-backed Knowledge helper.
- Preserved existing RAG behavior:
  - retrieved evidence blocks
  - source propagation
  - retrieval execution trace
  - fallback/degraded wording
- Added tests for Chat and Diet retrieval through Registry.

## Current Flow

```text
Chat/Diet -> retrieve_knowledge -> ToolRegistry -> knowledge.retrieve -> shared retriever
Search -> ToolRegistry -> search.tavily -> TavilySearchTool
```

## Verification

Executed:

```powershell
pytest tests\test_knowledge_registry_integration.py tests\test_tool_registry.py tests\test_rag_context.py -q
pytest tests\test_search_tool.py tests\test_diet_profile.py tests\test_integration.py tests\test_router.py -q
pytest -q
```

Results:

- `17 passed`
- `51 passed, 1 warning`
- Full regression: `170 passed, 2 skipped, 1 warning`

## Current Boundary

- ToolRegistry still does not replace LangGraph flow control.
- At this Knowledge step, Motion and MCP still called their tools directly in the main graph. Current status has advanced: MCP execute is now Registry-backed; Motion remains direct.
- Registry `timeout_seconds` remains policy metadata.

## Next Steps

- Consider whether selected registry metadata should be exposed through API execution metadata.
- Keep Motion migration conservative because of file, NumPy-array, media, and API boundaries.
