# 2026-07-09 ToolRegistry Stage Summary

## Type

Stage summary and documentation alignment.

## Background

The user decided to pause further ToolRegistry migration after MCP execute integration. This document consolidates the current state so later work does not confuse completed work, planned work, and deferred work.

## Completed In This Stage

| Path | Registry tool | Current status |
|---|---|---|
| Search | `search.tavily` | Main Search subgraph execution is Registry-backed |
| Knowledge/RAG | `knowledge.retrieve` | Chat/Diet retrieval uses Registry-backed Knowledge helper |
| MCP execute | `mcp.call_tool` | MCP `execute_tool_node` uses Registry while discovery/plan/format remain in the MCP subgraph |

## Not Migrated For Now

| Path | Reason |
|---|---|
| Motion media upload | File upload, size checks, temporary files, HTTP errors, and user-facing media behavior should stay in FastAPI/API boundary |
| Motion pose estimation | MediaPipe dependency, model file path, no-pose cases, and video decoding have richer operational errors than a simple tool call |
| Motion standard comparison | Candidate for later migration through `motion.compare_pose`, but paused for now |
| MCP production hardening | Real server discovered-tool allowlist, `inputSchema` deep validation, response ID matching, and process isolation are still production items |

## Current Interview Mouthpiece

> ToolRegistry is no longer only a design artifact. Search, Knowledge/RAG, and MCP execute are already real Registry-backed paths. I still do not describe it as a production-grade tool platform, because LangGraph continues to control business flow, MCP discovery/planning/formatting stay in the MCP subgraph, and Motion media/pose estimation remains outside Registry due to file, model, and API boundaries.

## Verification Already Recorded

- Search integration: full regression `166 passed, 2 skipped, 1 warning` at that step.
- Knowledge integration: full regression `170 passed, 2 skipped, 1 warning` at that step.
- MCP execute integration: full regression `172 passed, 2 skipped, 1 warning`.

## Paused Next Candidate

Motion standard pose comparison through `motion.compare_pose` remains a reasonable future candidate, but it is intentionally not started in this stage.
