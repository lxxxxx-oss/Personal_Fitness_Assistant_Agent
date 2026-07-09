# 2026-07-08 Interview Mouthpiece Alignment

## Type

Documentation alignment.

## Background

This project is interview-driven, so the study materials and project docs must use one consistent narrative. The previous documents still had several older expressions that could make the project sound inconsistent during an interview, especially around Chat/Diet boundaries, MCP positioning, Milvus evaluation status, and Motion completeness.

## Changes

- Unified Chat/Diet into the Knowledge capability domain.
- Clarified that Diet is an internal `diet_advice` path inside Knowledge, not an independent top-level capability domain.
- Clarified that MCP is a tool protocol supplement, not the main diet or knowledge chain.
- Updated Milvus wording to "real chain effect evaluation completed", while leaving broader Recall@K/MRR/faithfulness metrics as future production-grade extensions.
- Updated Motion wording to a complete standard action coach system: media input, PoseSequence, standard action comparison, and coaching-style feedback.
- Updated interview-facing files so the one-page cheat sheet, resume technology index, must-master story, deep-dive notes, and simulation notes use the same口径.

## Scope

Updated documentation only. No runtime code, API contract, or test implementation was changed.

## Verification

Ran a text scan for common conflicting phrases such as "current only Chat", "Chat RAG", "Milvus quality baseline pending", "Motion incomplete", and "Diet as independent chain". Remaining Diet mentions are intentionally kept as `Knowledge-Diet` or `diet_advice` internal-chain wording.

## Next Steps

- Keep `docs/interview/` focused on directly learnable interview material.
- When future implementation changes happen, continue separating "implemented", "current boundary", and "production upgrade path".
- If Milvus or Motion evaluation expands, update both the factual docs and the interview口径 together.
