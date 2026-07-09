# 2026-07-08 Minimal ToolRegistry Prototype

## Type

Feature implementation.

## Background

The interview narrative now distinguishes the internal tool system from MCP. To make that口径 defensible in code, the project needed a minimal `ToolRegistry` prototype that proves tool metadata, schema validation, permission labels, execution, retry, fallback, and audit logging can be centralized without rewriting the current LangGraph subgraphs.

## Changes

- Added `app/tools/registry.py`.
- Added `ToolSpec` for tool metadata and execution policy.
- Added `ToolRegistry` with:
  - `register`
  - `list_tools`
  - `get`
  - `validate_args`
  - `check_permission`
  - `execute`
  - bounded retry
  - fallback tool execution
  - minimal `audit_log`
- Added a small JSON-schema-like validator for object arguments.
- Added `build_default_tool_registry()` with representative tools:
  - `knowledge.retrieve`
  - `search.tavily`
  - `motion.compare_pose`
  - `mcp.call_tool`
- Exported registry types from `app.tools`.
- Added `tests/test_tool_registry.py`.

## Scope

This is a side-channel governance layer. It does not replace the existing LangGraph subgraph calls yet.

Current main flow:

```text
Router -> LangGraph subgraph -> existing tool
```

New optional governance entry:

```text
ToolRegistry.execute(tool_name, args, context) -> ToolResult
```

## Verification

Executed:

```powershell
pytest tests\test_tool_registry.py -q
pytest tests\test_tool_registry.py tests\test_search_tool.py tests\test_mcp_client.py tests\test_motion_tool.py -q
pytest -q
```

Results:

- `10 passed`
- `45 passed`
- Full regression: `165 passed, 2 skipped, 1 warning`

## Current Boundary

- `timeout_seconds` is recorded as policy metadata; the first prototype does not forcibly interrupt synchronous executors.
- ToolRegistry does not let LLM freely discover and call tools.
- Existing subgraphs still control execution order.
- MCP `inputSchema` validation against real server schemas is still a productionization item.

## Next Steps

- Consider migrating Search subgraph first because it is the lowest-risk tool path.
- Keep Motion and MCP migration cautious due to file, numeric-array, and subprocess boundaries.
