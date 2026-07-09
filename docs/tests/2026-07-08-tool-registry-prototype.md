# 2026-07-08 ToolRegistry Prototype Test

## Test Object

Minimal `ToolRegistry` prototype in `app/tools/registry.py`.

The test verifies:

- tool registration
- duplicate registration protection
- missing tool handling
- schema validation
- permission denial
- executor exception wrapping
- bounded retry
- fallback execution
- representative default tool registration
- default search tool execution in mock mode

## Commands

```powershell
pytest tests\test_tool_registry.py -q
pytest tests\test_tool_registry.py tests\test_search_tool.py tests\test_mcp_client.py tests\test_motion_tool.py -q
pytest -q
```

## Results

- `10 passed`
- `45 passed`
- Full regression: `165 passed, 2 skipped, 1 warning`

## Conclusion

The minimal registry prototype is usable as a side-channel tool governance layer. It does not yet replace the main LangGraph subgraph tool calls.

Current status note: this was the 2026-07-08 prototype state. Search, Knowledge/RAG, and MCP execute were later connected to registry execution. Motion remains a direct-call path, with migration evaluation recorded in `docs/technical/tool-registry/MOTION_MCP_REGISTRY_MIGRATION_EVALUATION.md`.

## Remaining Risk

- `timeout_seconds` is policy metadata only in this prototype.
- At this prototype step, Search, Motion, Knowledge, and MCP subgraphs were not yet migrated to call through the registry.
- MCP real server `inputSchema` validation remains a production hardening item.
