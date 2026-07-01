# 2026-07-01 Milvus RAG 后端测试记录

## 测试对象

本次测试覆盖 RAG Retriever 双后端改造：

- `MemoryRetriever` 原有分块、embedding 检索、threshold、clear、document_count 行为。
- `MilvusRetriever` 的 Collection 创建、upsert、search 结果结构。
- Milvus 不可用时 fallback 到 MemoryRetriever。
- Chat/API/Router 相关主链路在新增配置后不被破坏。

## 自动化测试命令

```powershell
pytest tests\test_retriever.py -q
```

结果：

```text
11 passed
```

继续执行相关回归：

```powershell
pytest tests\test_retriever.py tests\test_api.py tests\test_router.py -q
```

结果：

```text
56 passed, 1 warning
```

## 测试说明

- Milvus 单元测试使用 fake `pymilvus.MilvusClient`，不要求本机启动真实 Milvus。
- 测试验证了 Milvus 后端输出仍保持 `ToolResult.data = [{"content", "score", "index", "source"}]` 结构，保证 Chat/Diet 子图无需感知底层后端。
- fallback 测试验证了 Milvus 不可用时不会让 RAG 链路崩溃。

## 遗留风险

- 尚未执行真实 Milvus 服务集成测试。
- 尚未建立 RAG 标准问答集，因此不能报告真实 Recall@K、MRR 或线上准确率。
- 尚未验证 Docker profile 在另一台机器上的完整构建和启动。
