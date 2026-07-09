# 2026-07-09 Motion/MCP ToolRegistry Migration Evaluation

## Type

Design evaluation and interview mouthpiece alignment.

## Background

Search and Knowledge/RAG had already been routed through the minimal `ToolRegistry`. This evaluation decided whether Motion and MCP should be migrated immediately or kept as direct-call paths for that step. Current status has advanced: MCP execute was later routed through `mcp.call_tool`; Motion remains direct.

## Evaluation Summary

- Motion should not be migrated as one large tool. It includes media upload, temporary file handling, MediaPipe pose estimation, `PoseSequence`, reference selection, schema-safe comparison, numeric metrics, and coaching feedback.
- The most suitable Motion migration unit is only the `PoseSequence -> PoseSequence` comparison step, represented by `motion.compare_pose`.
- MCP is the better next migration candidate because its execute step already looks like `tool_name + arguments -> MCPClient.call_tool -> ToolResult`.
- At evaluation time, the registry already registered `motion.compare_pose` and `mcp.call_tool`, but the main Motion/MCP runtime paths still called their tools directly. MCP execute was later migrated.

## Decision

Do not migrate Motion/MCP in this step. Record the migration strategy first:

1. Migrate MCP `execute_tool_node` through `ToolRegistry.execute("mcp.call_tool", ...)`.
2. After MCP is verified, consider routing only Motion standard pose comparison through `motion.compare_pose`.
3. Keep media upload, pose estimation, temporary file management, and API-level HTTP errors outside Registry until there is a clear observability or governance need.

## Interview Value

This gives a stronger answer to the ToolRegistry follow-up:

- Registry is not decorative: Search and Knowledge/RAG were already real paths at evaluation time.
- Registry is not overused: Motion/MCP were delayed because their boundaries were riskier.
- The sequence was specific and defensible: MCP execution first, Motion compare later.

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

MCP execute-node Registry integration was completed later with targeted tests. Next candidate: Motion standard pose comparison.
