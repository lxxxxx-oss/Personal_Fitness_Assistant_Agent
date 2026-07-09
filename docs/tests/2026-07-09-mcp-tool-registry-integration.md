# 2026-07-09 MCP ToolRegistry Integration Test

## Test Object

MCP `execute_tool_node` integration with the minimal `ToolRegistry`.

## What Was Tested

- MCP execution calls `ToolRegistry.execute("mcp.call_tool", ...)`.
- Mock MCP recipe lookup still succeeds.
- Registry metadata is written into `_tool_result.meta` and `_mcp_tool_meta`.
- Registry audit log records `mcp.call_tool` execution.
- Invalid `arguments` shape is rejected as a structured `INVALID_PARAM` error.
- Existing MCP fallback behavior and ToolRegistry tests still pass.

## Commands

```powershell
pytest tests\test_mcp_client.py tests\test_tool_registry.py -q
pytest tests\test_integration.py tests\test_router.py tests\test_search_tool.py tests\test_knowledge_registry_integration.py -q
pytest -q
```

## Results

- `27 passed`
- `50 passed, 1 warning`
- Full regression: `172 passed, 2 skipped, 1 warning`

## Conclusion

MCP execute is now a real Registry-backed path. Search, Knowledge/RAG, and MCP execute are governed by the minimal `ToolRegistry`; Motion remains the only major non-Registry tool path.

## Remaining Risk

- Registry does not yet enforce discovered MCP tool allowlists.
- Registry does not validate against real MCP server `inputSchema`.
- `timeout_seconds` remains policy metadata; hard timeout is still handled inside `MCPClient`.
