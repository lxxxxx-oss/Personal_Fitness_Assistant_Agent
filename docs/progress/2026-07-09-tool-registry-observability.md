# 2026-07-09 ToolRegistry Observability

## Type

Feature enhancement.

## Background

After Search was routed through the minimal `ToolRegistry`, the next interview-relevant improvement was observability: a tool call should not be a black box. The registry needed stable fields that can be inspected in tool results and audit logs.

## Changes

- Added `execution_id` generation in `ToolRegistry.execute`.
- Added `duration_ms` measurement for every registry execution path.
- Added observability metadata to every returned `ToolResult.meta`:
  - `execution_id`
  - `tool_name`
  - `permission`
  - `attempts`
  - `timeout_seconds`
  - `duration_ms`
  - `fallback_from` when applicable
- Expanded `audit_log` entries with:
  - `execution_id`
  - `permission`
  - `duration_ms`
  - `fallback_from`
- Reused a caller-provided `context["execution_id"]` when present.
- Kept fallback calls under the same `execution_id`.

## Verification

Executed:

```powershell
pytest tests\test_tool_registry.py tests\test_search_tool.py -q
pytest -q
```

Results:

- `18 passed`
- Full regression: `167 passed, 2 skipped, 1 warning`

## Current Boundary

- `timeout_seconds` is still policy metadata and is not a hard cancellation mechanism.
- Audit data is currently in-memory and local to the registry instance.
- Search is the only subgraph currently routed through Registry.

## Next Steps

- Consider exposing selected registry observability fields in API execution metadata if useful for UI/debugging.
- Consider migrating Knowledge retrieval through Registry after Search remains stable.
