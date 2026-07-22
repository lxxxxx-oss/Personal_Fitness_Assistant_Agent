# Codex Session State

## Current Task

- Status: active
- Goal: 重建 Milvus 权威知识索引，并运行 19 条完整 RAGAS 真实生成与裁判评测。
- Updated: 2026-07-22

## Completed

- 可索引知识文档由 5 份扩展为 12 份，覆盖力量训练、身体活动、运动蛋白、肌酸、健康膳食、体重管理、补液和睡眠恢复。
- 新条目来自 ACSM、WHO、中国居民膳食指南、ISSN、CDC/NIDDK、NATA 与 AASM；采用中文结构化转述，保留原始链接、适用范围、安全边界和核验日期，不整篇复制网页或论文。
- 修正旧知识中的固定宏量比例、统一饮水量、蛋白质绝对伤肾等过度简化表述。
- 保留上一阶段 RAG 分块 v2：标题层级、段落/句子装箱、真实相邻块重叠、`section_path`、新 Milvus collection 与旧 schema 兼容。
- RAG 黄金集扩展为 21 条：19 条可回答、2 条无答案；同步更新 README、项目总览、运行与排错、项目证据和 interview 文档。

## Verification

- 专项回归：`42 passed`。
- 全量回归：`247 passed, 2 skipped, 1 warning in 24.98s`；warning 为第三方 Starlette TestClient 弃用提示。
- 本地真实 embedding + MemoryRetriever：12 个文件生成 81 个 chunk；19 条可回答样例的 `source_hit@5` 与 `evidence_hit@5` 均为 `19/19`，阈值 `0.5`。
- 上述结果是检索冒烟，不是完整 RAGAS 三指标基线；完整 19 条生成与裁判评测仍可后续执行。

## Boundary

- `data/knowledge/` 中 PDF 仅作参考；当前自动入库只读取 `.txt` / `.md`。
- 现有持久化 Milvus 若仍保存旧知识，需要重新启动入库流程或重建默认 collection 才能使用新增内容。
- 本轮修改尚未提交或推送。

## Next Steps

- 确认 Milvus、生成模型和本地裁判模型的可用状态。
- 将 12 份知识文档重新索引到新的默认 Collection。
- 运行 19 条完整 RAGAS 三指标评测，记录结果并同步项目证据与面试口径。

## Resume Prompt

继续当前项目：先读 AGENTS.md 和本文件，再检查 git status。权威知识库扩充与文档同步已完成；如需继续，优先重建 Milvus 并运行 19 条完整 RAGAS 基线，不要把 19/19 检索冒烟表述为端到端 RAGAS 得分。
