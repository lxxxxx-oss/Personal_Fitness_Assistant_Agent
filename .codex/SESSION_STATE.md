# Codex Session State

> 注意：本段为 2026-07-31 最新交接状态；下方若出现乱码旧内容，视为已废弃。

## Current Task

- Status: idle
- Goal: 将近期 RAG / RAGAS / 检索指标相关问答整理进面试学习文档。
- Updated: 2026-07-31

## Progress

- 已把用户追问和推荐回答整理到 `docs/learning/04_高频技术问答.md`，覆盖 Recall@5、MRR、BM25、RRF、RRF vs MRR、为什么 Dense/Hybrid 分开评测、Hybrid MRR 如何提升。
- 已同步更新 `docs/learning/03_简历技术点总表.md`、`02_项目讲解与面试话术.md`、`07_面试前速记.md`、`08_模拟面试.md`、`09_简历项目描述与防守边界.md`、`11_求职投递与打招呼策略.md`、`00_RESUME_TECH_INDEX.md`、`06_技术深挖与白板.md`、`README.md`。
- 统一了最新事实口径：Dense `Recall@5=0.895, MRR=0.833`；Hybrid `Recall@5=0.947, MRR=0.816`；RAGAS 本地裁判单样例 smoke 为 context `1.000`、faithfulness `1.000`、answer relevance `0.988`。

## Key Decisions

- 面试中可以说 Hybrid 提升了 Top-5 召回覆盖，但因 MRR 略低，不能说“所有检索质量指标全面提升”。
- RAGAS 单样例 smoke 只能证明链路跑通和兼容性，完整 19 条生成质量基线尚未稳定复现。
- `eval_retrieval.py` 的 Dense/Hybrid 对比是开发诊断和消融实验，不是线上运行时拆成两个 RAG 系统。

## Verification

- `rg` 已检查 `docs/learning` 中旧口径关键词，未保留过期 Dense 19/19 表述。
- `git diff --check` 已运行，无空白格式错误；仅出现 Windows CRLF warning。

## Next Steps

- 若继续增强面试证据，优先分批跑完整 19 条可回答样例 RAGAS 基线。
- 若要交付当前整理结果，下一步可检查 diff 后提交。

## Resume Prompt

继续本项目：先读 `AGENTS.md`、`.codex/SESSION_STATE.md`、`git status --short` 和 `docs/project/README.md`。当前已把近期 RAG 指标、BM25/RRF/MRR、Dense/Hybrid 消融和 RAGAS smoke 结论整理进 `docs/learning/`；注意完整 19 条 RAGAS 生成质量基线尚未稳定复现。
