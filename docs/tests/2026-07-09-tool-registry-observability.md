# 2026-07-09 ToolRegistry Observability Test

## Test Object

ToolRegistry observability fields in `ToolResult.meta` and `audit_log`.

## What Was Tested

- Successful tool calls include `execution_id`.
- Successful tool calls include `duration_ms`.
- Missing-tool failures still include observability metadata.
- Fallback calls reuse the same `execution_id`.
- Caller-provided `context["execution_id"]` is preserved.
- Audit log entries include `execution_id` and `duration_ms`.
- Search subgraph still works with the registry-backed search tool.

## Commands

```powershell
pytest tests\test_tool_registry.py tests\test_search_tool.py -q
pytest -q
```

## Results

- `18 passed`
- Full regression: `167 passed, 2 skipped, 1 warning`

## Conclusion

Registry-backed tool calls are now observable enough to support interview discussion around tracing, duration measurement, fallback attribution, and auditability.

## Remaining Risk

- `timeout_seconds` is policy metadata only.
- Audit logs are not persisted.
- Only Search currently uses Registry in the main graph.
