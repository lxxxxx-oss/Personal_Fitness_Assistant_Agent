# 2026-07-10 Memory + Context + RAG 统一 Benchmark 验收

## 测试对象

本次测试验证 Memory、Context Compression 和 RAG 在同一条 Agent 链路中的联动稳定性，重点不是单个函数是否可用，而是组合后是否满足面试可讲的工程闭环：

- 长期记忆可以被召回。
- 敏感长期记忆不会绕过候选确认。
- 长期记忆可以进入 Prompt Builder。
- 超长上下文会触发 compact，并保持 prompt 长度受控。
- RAG evidence 的来源和引用标识可以被透传。

## 测试数据

数据集位置：

```text
data/eval/memory_context_benchmark.jsonl
```

当前包含 8 条样本，覆盖 5 个 category：

| category | 样本数 | 验证点 |
|---|---:|---|
| `memory_recall` | 2 | 长期记忆写入后，能通过检索召回 |
| `sensitive_candidate` | 2 | 伤病、过敏等健康信息进入 candidate，不直接写正式 memory |
| `prompt_memory_injection` | 1 | 检索到的长期记忆会进入 prompt |
| `compact` | 1 | 长上下文触发 compact，最终 prompt 不超过预算 |
| `rag_source` | 2 | RAG context 生成和去重后的 source 透传正确 |

## 执行命令

```powershell
python scripts\eval_memory_context.py --fail-on-fail
pytest tests\test_memory_context_eval_script.py -q
pytest tests\test_memory_context_eval_script.py tests\test_memory_store.py tests\test_conversation_store.py tests\test_api.py tests\test_integration.py tests\test_sliding_window.py tests\test_search_tool.py tests\test_mcp_client.py tests\test_tool_registry.py tests\test_knowledge_registry_integration.py tests\test_rag_context.py tests\test_router.py tests\test_milvus_retriever.py tests\test_config.py -q
```

## 真实结果

```text
Memory/Context benchmark: 8/8 passed (100.00%)
- compact: 1/1 (100.00%)
- memory_recall: 2/2 (100.00%)
- prompt_memory_injection: 1/1 (100.00%)
- rag_source: 2/2 (100.00%)
- sensitive_candidate: 2/2 (100.00%)
```

自动化测试结果：

- `tests/test_memory_context_eval_script.py`：2 passed。
- 核心回归集：137 passed，1 warning。

warning 为 Starlette TestClient/httpx 兼容层弃用提示，不影响本次验收结论。

## 结论

当前已经具备 Memory + Context Compression + RAG 的最小统一评测闭环。它可以用于面试中解释“如何判断优化有效”，也可以作为后续修改 Memory、Prompt Builder、RAG 检索逻辑时的回归保护。

## 遗留风险

- 样本规模还小，不能代表真实生产效果。
- 当前主要验证链路正确性，尚未评估大规模 Recall@K、MRR、生成忠实度和延迟。
- 敏感记忆识别仍是规则级原型，后续如果接入 LLM candidate extractor，需要新增误写率和误拒率评测。
