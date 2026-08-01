# Codex Session State

## Current Task

- Status: idle
- Goal: 扩展 RAG 评测集、收紧生成证据约束，并完成 tuning 对照验证。
- Updated: 2026-08-01

## Completed

- 黄金集扩展为 80 条：60 条可回答、20 条无答案；55 条 tuning、25 条 holdout，并补齐 split、难度、领域和问法类型元数据。
- `eval_retrieval.py` 与 `eval_rag.py` 支持分区、分层报告、分阶段执行、断点续跑和配置指纹；RAGAS 仍是主评测，Recall@K/MRR 只作检索诊断。
- Chat 升级为 `grounded-v3`：只依据检索证据，保留否定和适用条件，不混合人群/剂量阶段，证据不足即停止，关键结论使用 `[RefN]`；普通和流式路径统一为 `max_tokens=512`、`temperature=0`、`top_p=1`。
- 42 条可回答 tuning 已完成前后两轮真实生成、本地 RAGAS 评分和重点失败样例人工复核；项目事实文档与面试材料已同步。
- 未运行 18 条可回答 holdout，避免调参期间污染最终验收；未改动未跟踪的 `docs/interview/`。

## Key Results

- 60 条可回答样例：Dense/Hybrid Recall@5 均为 `0.967`，MRR 为 `0.844/0.895`。
- 42 条 tuning RAGAS：`1.000/0.725/0.788 -> 1.000/0.897/0.798`；忠实度中位数 `0.800 -> 1.000`，忠实度低于 `0.5` 的样例 `8 -> 3`。
- 人工审计仍发现 Top-1 排序/证据覆盖问题、小模型残余越界和本地 8B 量化裁判假阴性，因此当前数字是调参证据，不是生产或 holdout 泛化结论。

## Verification

- 全量测试：`326 passed, 1 skipped, 2 warnings`。
- `git diff --check` 通过；文档旧口径搜索通过。
- grounded-v3 生成约 `6m19s`，评分约 `14m08s`，进度文件为 `tmp/rag_eval_hybrid_tuning_grounded_v3_20260801.json`。

## Next Steps

1. 当前配置冻结后，只运行一次 18 条可回答 holdout，作为最终泛化验收。
2. 若 holdout 暴露排序问题，优先单独评估 reranker；不要继续向 prompt 堆样例特判。

## Resume Prompt

继续 RAG 验收：先确认当前配置已冻结，再仅运行一次 18 条可回答 holdout，比较 RAGAS 与人工抽检结果。不要改动未跟踪的 `docs/interview/`。
