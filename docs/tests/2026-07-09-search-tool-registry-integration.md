# 2026-07-09 Search ToolRegistry Integration Test

## Test Object

Search subgraph integration with the minimal `ToolRegistry`.

## What Was Tested

- Search subgraph calls `ToolRegistry.execute("search.tavily", ...)`.
- Mock search still records the same execution trace.
- Registry metadata is available in `_search_meta`.
- Search tool failure still produces degraded execution and route warnings.
- Full project regression remains green.

## Commands

```powershell
pytest tests\test_search_tool.py tests\test_tool_registry.py -q
pytest -q
```

## Results

- `17 passed`
- Full regression: `166 passed, 2 skipped, 1 warning`

## Conclusion

Search is the first real subgraph path connected to `ToolRegistry`. The integration preserves existing Search behavior while proving the registry can govern a live subgraph tool call.

## Remaining Risk

- Registry observability was minimal at this step; later `2026-07-09-tool-registry-observability.md` added `execution_id`, `duration_ms`, and richer audit fields.
- Motion, Knowledge, and MCP have not been migrated to registry execution.
- `timeout_seconds` is still policy metadata rather than hard cancellation.
