# 2026-07-08 Tool System and Minimal ToolRegistry Design

## Type

Documentation design update.

## Background

Interview materials needed a clearer distinction between the project's internal tool system and MCP. The previous wording could make it sound like MCP was the whole tool system, while the actual architecture already has internal tool contracts through `ToolResult`, `ErrorCode`, validators, Pydantic models, `PoseSequence`, and LangGraph subgraph boundaries.

## Changes

- Added a dedicated interview study note: `docs/interview/05_TOOL_SYSTEM_REGISTRY_DESIGN.md`.
- Clarified the core口径: internal tools are deterministic capability units with input contracts, permission boundaries, executors, unified results, and recoverable errors.
- Clarified that MCP is an external tool protocol supplement, not the whole tool system.
- Added a minimal `ToolSpec + ToolRegistry` design for future implementation.
- Updated the interview README, technology index, Q&A, one-page cheat sheet, deep-dive notes, project story, and main docs to reference the same口径.

## Current Boundary

No runtime code was changed. The current project remains a lightweight convention-based tool system:

- Tools are still called by domain subgraphs.
- There is no central `ToolRegistry` class yet.
- Tool metadata, timeout, retry, fallback, and audit are not centralized.
- `ToolResult/ErrorCode` and subgraph boundaries are the current shared contract.

## Next Steps

- If implementation starts, add a minimal registry around existing tools without changing core business behavior.
- Keep LangGraph responsible for task flow and ToolRegistry responsible only for tool execution governance.
- Keep MCP positioned as one external tool source that can be managed by the registry.
