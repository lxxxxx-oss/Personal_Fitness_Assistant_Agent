# 2026-07-09 MCP ToolRegistry Integration

## Type

Feature integration.

## Background

After Search and Knowledge/RAG were routed through the minimal `ToolRegistry`, the next evaluated step was MCP. MCP's execute step already has a clean shape:

```text
tool_name + arguments -> MCPClient.call_tool -> ToolResult
```

That makes it a suitable migration target without rewriting MCP discovery, planning, or formatting.

## Changes

- Added `get_mcp_tool_registry()` in `app/graph/subgraphs/mcp.py`.
- Registered a subgraph-local `mcp.call_tool` `ToolSpec`.
- The MCP registry executor reuses the existing `_get_client()` path, preserving:
  - configured real server connection
  - missing real server fallback to mock
  - mock demo mode
- Routed `execute_tool_node` through:

```text
ToolRegistry.execute(
  "mcp.call_tool",
  {"tool_name": tool_name, "arguments": arguments},
  context={"allowed_permissions": ["subprocess"]}
)
```

- Stored registry execution metadata in `_mcp_tool_meta`.
- Added tests for:
  - mock MCP tool execution through Registry
  - registry metadata and audit log
  - schema failure when `arguments` is not an object

## Current Flow

```text
MCP discover -> MCP plan -> ToolRegistry -> mcp.call_tool -> MCPClient.call_tool -> MCP format
```

Search and Knowledge/RAG were already Registry-backed:

```text
Search -> ToolRegistry -> search.tavily
Knowledge/RAG -> ToolRegistry -> knowledge.retrieve
```

## Verification

Executed:

```powershell
pytest tests\test_mcp_client.py tests\test_tool_registry.py -q
pytest tests\test_integration.py tests\test_router.py tests\test_search_tool.py tests\test_knowledge_registry_integration.py -q
pytest -q
```

Results:

- `27 passed`
- `50 passed, 1 warning`
- Full regression: `172 passed, 2 skipped, 1 warning`

## Current Boundary

- Registry controls MCP execute metadata, permission label, schema validation, and audit log.
- Registry does not replace MCP discovery, planning, or result formatting.
- Registry `timeout_seconds` is still policy metadata; actual subprocess/read timeout remains inside `MCPClient`.
- Real server `inputSchema` deep validation, discovered-tool allowlist, response ID matching, and process isolation remain production hardening items.

## Deferred Candidate

- Motion standard pose comparison through `motion.compare_pose` remains a later candidate, but the current ToolRegistry stage is paused.
- Keep Motion media upload and pose estimation controlled by FastAPI/API boundaries.
