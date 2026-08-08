# Codex Session State

## Current Task

- Status: idle
- Goal: 已完成父子分块 RAGAS 与开放式多意图路由相关文档收尾及全量验证，准备提交并推送 GitHub。
- Updated: 2026-08-08

## Progress

- RAG/检索专项测试通过：63 passed，1 个第三方弃用警告。
- 当前内存索引：12 个知识文件、87 个父级检索单元。
- 全量检索评测：Dense Recall@5/MRR=0.9667/0.8436；Hybrid=0.9667/0.8931。
- Hybrid 分拆：tuning=0.9524/0.8710；holdout=1.0000/0.9444。
- Qwen3-0.6B 生成与 Qwen3-8B GGUF 裁判闭环通过。
- 父子分块版 tuning 已完成 42/42：RAGAS=1.000/0.902/0.786，生成约 6 分 41 秒、评分约 14 分 56 秒。
- 父子分块版 holdout 已完成 18/18：RAGAS=1.000/0.815/0.762，生成约 2 分 58 秒、评分约 7 分 21 秒。

## Touched Files

- `.codex/SESSION_STATE.md`
- 新评测输出：`tmp/rag_retrieval_parent_child_20260808.json`
- 新烟测进度：`tmp/rag_eval_parent_child_smoke_20260808.json`
- tuning 进度：`tmp/rag_eval_parent_child_tuning_20260808.json`
- holdout 进度：`tmp/rag_eval_parent_child_holdout_20260808.json`
- 已同步 `docs/project/` 的项目证据、运行排错、项目总览和 RAG 技术状态。
- 已同步 `docs/learning/` 的项目讲解、简历技术点、问答、白板、速记和模拟面试等口径。
- 工作区原有 Router 改动及未跟踪 `docs/interview/` 均不触碰。

## Key Decisions

- 本轮新评测使用独立进度/输出文件，不覆盖 2026-08-01 的旧单层基线。
- 固定 Hybrid 参数：Top-5、candidate-k=20、RRF k=60、Dense threshold=0.0。
- 先完成单例生成/评分闭环，再跑 42 条 tuning 和 18 条 holdout。

## Verification

- `pytest`：63 passed。
- 检索评测：80 条（60 可回答、20 不可回答），Hybrid 相比 Dense 的 MRR +0.0494。
- tuning RAGAS：42 条全部评分成功，context_relevance=1.000、faithfulness=0.902、answer_relevance=0.786。
- holdout RAGAS：18 条全部评分成功，context_relevance=1.000、faithfulness=0.815、answer_relevance=0.762。
- Markdown 本地链接检查通过；`git diff --check` 无补丁格式错误。
- 上传前全量回归：`333 passed, 1 skipped, 2 warnings`，用时 `22.47s`。

## Next Steps

1. 当前阶段无必做代码工作；后续若继续 RAG 优化，优先人工复核 holdout 低分样例。
2. `docs/interview/` 保持本地未跟踪，不纳入本次 GitHub 提交。

## Resume Prompt

当前代码与文档已验证；若继续优化，以 2026-08-08 父子分块复测及开放式多意图路由作为当前事实口径。
