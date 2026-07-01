# 2026-07-01 Milvus RAG 后端实现

## 背景

项目最初为了保证本地轻量可运行，RAG 使用 `Sentence-Transformers + NumPy` 内存向量检索。简历中包含 Milvus 技术点，因此本次补齐可选 Milvus 后端，但保留 Memory fallback，避免本地未启动 Milvus 时影响演示。

## 变更概述

- 新增 `MilvusRetriever`，与 `MemoryRetriever` 保持相同调用接口：`add_documents`、`search`、`clear`、`document_count`。
- 新增 `RETRIEVER_BACKEND=memory|milvus` 配置切换。
- 新增 Milvus 配置：`MILVUS_URI`、`MILVUS_COLLECTION`、`MILVUS_RECREATE_COLLECTION`、`MILVUS_INDEX_TYPE`、`MILVUS_METRIC_TYPE`、`MILVUS_NLIST`、`MILVUS_NPROBE`。
- `Chat` 和 `Diet` 子图改为读取 `RETRIEVER_TOP_K` 和 `RETRIEVER_THRESHOLD`，不再写死检索参数。
- 知识库加载时传入 source 文件名，RAG Prompt 可以展示来源。
- `docker-compose.yml` 增加 Milvus、etcd、MinIO，放入 `milvus` profile，默认不启动重依赖服务。
- 新增 `pymilvus` 依赖。

## 工程取舍

1. 默认仍使用 MemoryRetriever，保证项目无需 Milvus 也能完整运行。
2. 启用 Milvus 后，如果连接、建表、写入或搜索失败，会 fallback 到 MemoryRetriever。
3. Milvus schema 先保留最小字段：`id`、`content`、`source`、`embedding`。
4. 文档去重使用 `source + content` 的 hash 作为主键，避免同一 chunk 重复插入。
5. 当前实现补齐了真实后端切换能力，但还没有做真实大规模 Recall@K、MRR 和 P95 latency 评测。

## 验证结果

已执行：

```powershell
pytest tests\test_retriever.py -q
pytest tests\test_retriever.py tests\test_api.py tests\test_router.py -q
```

结果：

```text
11 passed
56 passed, 1 warning
```

warning 来自 FastAPI/Starlette TestClient 兼容层，不影响本次 RAG 行为。

## 后续计划

1. 启动真实 Milvus 服务执行手工集成测试。
2. 建立 RAG 标准问答与证据片段标注集。
3. 记录 Recall@K、MRR、无关片段比例、P95 latency。
4. 根据评测结果比较 Memory、Milvus、reranker 和不同 chunk 策略。
