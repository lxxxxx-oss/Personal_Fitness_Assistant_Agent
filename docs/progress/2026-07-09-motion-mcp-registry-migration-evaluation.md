# 2026-07-09 Motion/MCP ToolRegistry Migration Evaluation

## Type

Design evaluation and interview mouthpiece alignment.

## Background

Search and Knowledge/RAG have already been routed through the minimal `ToolRegistry`. The remaining question is whether Motion and MCP should be migrated immediately or kept as direct-call paths for now.

## Evaluation Summary

- Motion should not be migrated as one large tool. It includes media upload, temporary file handling, MediaPipe pose estimation, `PoseSequence`, reference selection, schema-safe comparison, numeric metrics, and coaching feedback.
- The most suitable Motion migration unit is only the `PoseSequence -> PoseSequence` comparison step, represented by `motion.compare_pose`.
- MCP is the better next migration candidate because its execute step already looks like `tool_name + arguments -> MCPClient.call_tool -> ToolResult`.
- The current registry already registers `motion.compare_pose` and `mcp.call_tool`, but the main Motion/MCP runtime paths still call their tools directly.

## Decision

Do not migrate Motion/MCP in this step. Record the migration strategy first:

1. Migrate MCP `execute_tool_node` through `ToolRegistry.execute("mcp.call_tool", ...)`.
2. After MCP is verified, consider routing only Motion standard pose comparison through `motion.compare_pose`.
3. Keep media upload, pose estimation, temporary file management, and API-level HTTP errors outside Registry until there is a clear observability or governance need.

## Interview Value

This gives a stronger answer to the ToolRegistry follow-up:

- Registry is not decorative: Search and Knowledge/RAG are already real paths.
- Registry is not overused: Motion/MCP are delayed because their boundaries are riskier.
- The next step is specific and defensible: MCP execution first, Motion compare later.

## Verification

No code behavior was changed in this step, so no automated test run was required.

## Updated Docs

- `docs/technical/tool-registry/MOTION_MCP_REGISTRY_MIGRATION_EVALUATION.md`
- `docs/technical/README.md`
- `docs/README.md`
- `docs/interview/05_TOOL_SYSTEM_REGISTRY_DESIGN.md`
- `docs/interview/面试模拟.md`
- `docs/progress/README.md`

## Next Step

Implement MCP execute-node Registry integration with targeted tests.
