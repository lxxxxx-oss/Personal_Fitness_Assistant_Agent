# Codex Session State

## Current Task

- Status: idle
- Goal: 已完成 `docs/` 全量梳理；保留真实 Milvus 与 19 条 RAGAS 评测的跨电脑续跑现场。
- Updated: 2026-07-22

## Completed

- 已审计 39 份 Markdown 文档，确认核心事实、interview、technical、optimization、miniprogram、superpowers/旧版归档的职责和优先级清晰。
- `docs/README.md` 已补完整分区入口和小程序职责；全部非 README 文档均可由对应目录索引访问。
- 修正《项目总览》中“目录存在 PDF”的错误：当前知识目录是 12 份 `.txt/.md`，没有 PDF，也未接入 PDF 解析。
- 小程序索引已把历史文件名“实施计划”明确标注为当前验收计划；技术索引将工具注册表专题标为接入状态。
- active 文档对“四类产品能力/五个代码 intent”“19/19 检索冒烟/未完成 19 条 RAGAS 基线”“小程序代码闭环/未完成真机验收”的表述一致。
- 已确认旧任务中断在“新 Milvus Collection 尚无完整验证证据、19 条端到端 RAGAS 尚无结果”。
- `scripts/eval_rag.py` 已支持 `memory/milvus` 显式后端；Milvus 评测不启用内存 fallback，避免污染结果口径。
- 已支持 `generate/score/all` 分阶段执行、逐条原子保存、断点跳过、`--max-new-cases` 分批生成、`--case-id` 小范围验证和 `--fresh` 重置。
- 进度配置以数据集和知识库内容指纹校验，不绑定绝对目录，可随同版本一致的数据跨电脑续跑。
- README、项目总览、运行排错、项目证据和面试技术点已同步；文档继续明确“完整 19 条基线尚未运行”。

## Touched Files

- 本轮文档整理：`docs/README.md`、`docs/miniprogram/README.md`、`docs/technical/README.md`、`docs/项目总览.md`、`.codex/SESSION_STATE.md`。
- 之前尚未提交的 RAG 工作：`README.md`、`docs/interview/03_简历技术点总表.md`、`docs/运行与排错.md`、`docs/项目证据.md`、`scripts/eval_rag.py`、`tests/test_rag_eval_script.py`。

## Verification

- 本机仅执行无外部服务的专项回归：`48 passed, 1 warning in 33.02s`。
- 覆盖 Retriever、Milvus、RAG 上下文与评测入口；其中评测入口 13 项。
- 文档验收：39 份 Markdown、0 个失效相对链接、0 份未被目录索引覆盖的非 README 文档；`git diff --check` 通过。
- warning 是 LangGraph serializer 的待弃用提示，与本次变更无关。
- 本机没有启动 Milvus、加载生成/裁判模型或运行真实 RAGAS，不能记录新的语义分数。

## Boundary / Interruption Point

- 默认新 Collection 仍为 `fitness_knowledge_bge_small_zh_v15_chunk_v2`；另一台电脑的持久化卷状态未知，统一按“尚未验证重建完成”处理。
- 当前知识加载器自动索引 12 份 `.txt/.md`，预期结构感知分块为 81 个 chunk；当前目录没有 PDF，加载器也未接入 PDF 解析。
- 19/19 正确来源与关键证据命中只是 MemoryRetriever 检索冒烟，不等于 Milvus 端到端或 RAGAS 基线。

## Next Steps

1. 后续在模型电脑继续原 RAG 收尾：先验证 1 条 Milvus 无 fallback，再分批生成 19 条并运行 RAGAS 三指标评分。
2. 完成真实评测后，把命令、环境、分项结果和边界写入 `docs/项目证据.md`，同步更新总览、运行说明和面试口径。

## Resume Prompt

继续 RAG 真实评测收尾：先读 AGENTS.md、`.codex/SESSION_STATE.md` 并检查 git status。文档全量梳理已完成，RAG 评测入口改造专项测试 48 passed；在具备 Milvus、生成模型和 RAGAS 裁判的电脑先跑 1 条 Milvus 无 fallback，再断点生成 19 条并评分，完成后同步项目证据和面试口径。
