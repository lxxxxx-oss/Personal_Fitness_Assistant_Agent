# 2026-07-09 Search ToolRegistry Integration

## Type

Feature integration.

## Background

The minimal `ToolRegistry` had already been implemented as a side-channel governance layer. The next lowest-risk step was to connect one real subgraph to it, proving that the registry is not only a design artifact while avoiding the higher complexity of Motion file/array handling and MCP subprocess behavior.

## Changes

- Updated `app/graph/subgraphs/search.py` to execute search through `ToolRegistry.execute("search.tavily", ...)`.
- Replaced the Search subgraph's direct `TavilySearchTool` singleton with a registry singleton.
- Preserved the existing Search workflow:
  - query understanding
  - Tavily/mock search
  - answer synthesis
  - execution trace
  - degraded warning behavior
- Updated Search tests to verify:
  - registry-backed mock search execution
  - registry metadata in `_search_meta`
  - degraded warning behavior when the registered Search tool fails

## Scope

Search is now the first production path connected to the minimal registry.

Current status:

```text
Router -> Search subgraph -> ToolRegistry -> search.tavily -> TavilySearchTool
```

Other subgraphs still call their tools directly.

## Verification

Executed:

```powershell
pytest tests\test_search_tool.py tests\test_tool_registry.py -q
pytest -q
```

Results:

- `17 passed`
- Full regression: `166 passed, 2 skipped, 1 warning`

## Current Boundary

- ToolRegistry still does not replace LangGraph; LangGraph controls task flow.
- ToolRegistry does not let the LLM freely discover or call tools.
- Motion and MCP remain direct-call paths for now because their data and process boundaries are riskier.

## Next Steps

- Add richer registry observability such as `execution_id` and `duration_ms`.
- Consider gradually routing Knowledge retrieval through the registry after Search remains stable.
- Keep Motion and MCP migrations conservative.
