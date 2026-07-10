# 2026-07-10 Memory + Context + RAG 统一 Benchmark

## 类型

评测脚本新增、回归测试、优化路线收尾。

## 背景

前面已经分别完成了会话持久化、长期记忆、候选记忆确认、SQLite FTS5/LIKE 检索、可选 Milvus 用户记忆同步，以及 Prompt Builder 与确定性 compact。单点测试可以证明每个模块可用，但面试时还需要回答一个更关键的问题：

> 这些能力组合起来以后，怎么证明 Agent 真的更稳、更可控，而不是只堆了功能？

因此本阶段新增一个统一 benchmark，把 Memory、Context Compression 和 RAG 证据链放到同一套可重复评测中。

## 本次变更

- 新增 `data/eval/memory_context_benchmark.jsonl`，作为 Memory/Context/RAG 联动评测样本集。
- 新增 `scripts/eval_memory_context.py`，支持命令行执行、按 category 统计通过率、输出失败 case。
- 新增 `tests/test_memory_context_eval_script.py`，把 benchmark 纳入 pytest 回归。
- Benchmark 覆盖 5 类能力：
  - `memory_recall`：长期记忆能否被召回。
  - `sensitive_candidate`：健康/过敏等敏感记忆是否先进候选区，而不是直接进入正式长期记忆。
  - `prompt_memory_injection`：长期记忆能否被 Prompt Builder 注入回答上下文。
  - `compact`：长上下文是否触发 compact，并保证最终 prompt 不超过预算。
  - `rag_source`：RAG evidence 的来源和引用标识是否正确透传。

## 工程取舍

- 这套 benchmark 不是大规模生产评测，而是面试和原型阶段的最小可解释评测闭环。
- 样本规模先保持小而清晰，重点证明评测方法、指标切片和回归机制已经具备。
- 当前指标以 pass rate 和 category pass rate 为主；后续可以扩展 Recall@K、MRR、faithfulness、latency 和多轮任务成功率。

## 验证结果

已执行：

```powershell
python scripts\eval_memory_context.py --fail-on-fail
pytest tests\test_memory_context_eval_script.py -q
pytest tests\test_memory_context_eval_script.py tests\test_memory_store.py tests\test_conversation_store.py tests\test_api.py tests\test_integration.py tests\test_sliding_window.py tests\test_search_tool.py tests\test_mcp_client.py tests\test_tool_registry.py tests\test_knowledge_registry_integration.py tests\test_rag_context.py tests\test_router.py tests\test_milvus_retriever.py tests\test_config.py -q
```

真实结果：

- `scripts/eval_memory_context.py`：8/8 passed，整体通过率 100%。
- 单测：`tests/test_memory_context_eval_script.py`，2 passed。
- 核心回归集：137 passed，1 warning。

warning 来源于 Starlette TestClient/httpx 兼容层弃用提示，不影响本次功能。

## 面试表达

可以这样讲：

> 我没有只说“Agent 有记忆、有 RAG、有上下文压缩”，而是把它们放进统一 benchmark 里做回归。评测样本会检查长期记忆能不能召回、敏感信息会不会误写、记忆能不能进入 prompt、长上下文会不会被压缩，以及 RAG 的来源能不能透传。这样每次改 Memory、Prompt 或 RAG 时，都能判断链路是不是变稳了，而不是凭感觉说优化有效。

## 后续

- 扩充真实健身问答与饮食问答样本，增加 Recall@K 和 MRR。
- 增加生成忠实度评测，检查回答是否基于 evidence。
- 增加长对话任务成功率和多轮记忆一致性样本。
