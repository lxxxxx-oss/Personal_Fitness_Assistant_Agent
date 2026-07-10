# 2026-07-10 Memory Phase 6：Milvus 用户长期记忆增强

## 操作类型

功能增强 / 可选 Milvus 派生索引 / API 变更 / 测试补充 / 文档同步

## 变更概述

按照 `docs/optimization/IMPLEMENTATION_SEQUENCE.md` 的第七步，完成 Memory Phase 6 的最小闭环。

本次新增能力：

- SQLite 新增 `embedding_jobs`
- 新增配置：
  - `MEMORY_MILVUS_ENABLED`
  - `MEMORY_MILVUS_COLLECTION_NAME`
- 正式长期记忆创建/更新后，在启用语义增强时创建 pending embedding job
- 新增同步任务接口：
  - `GET /memory/embedding-jobs`
  - `POST /memory/embedding-jobs/process`
- 复用现有 `MilvusRetriever`
  - 用户长期记忆使用独立 Collection，默认 `fitness_user_memory`
  - Milvus row 的 `source` 存储 `memory_id`
- `/memory/search` 合并：
  - SQLite FTS5 / LIKE 关键词结果
  - Milvus 语义结果
  - importance 与 access_count 加权
- Milvus 同步失败时，job 标记 failed，并按有限重试策略等待后续处理
- Milvus 不可用时，SQLite 检索仍可工作，聊天主链路不受影响

## 当前边界

- 这是本地原型级 worker 接口，不是常驻后台进程
- 默认 `MEMORY_MILVUS_ENABLED=false`，避免本地演示依赖 Milvus
- 当前不主动删除 Milvus 中的旧向量；检索时以 SQLite active memory 过滤为准
- 真实 Milvus 服务仍需在另一台电脑按集成清单验证
- 尚未实现 memory eval 的 Recall@K/MRR 指标

## 影响范围

- `app/config.py`
- `app/memory/memory_store.py`
- `app/main.py`
- `tests/test_memory_store.py`
- `tests/test_api.py`
- `docs/API.md`
- `docs/README.md`

## 验收结果

见 `docs/tests/2026-07-10-memory-phase6-milvus-user-memory.md`。

## 面试口径

可以这样解释：

> 我没有把 Milvus 当成记忆系统的主存储，SQLite 仍然是 source of truth。Milvus 只是长期记忆的语义召回增强：写入正式 memory 后生成 embedding job，worker 成功后把内容同步到用户记忆 Collection。检索时合并 FTS5/LIKE 和 Milvus 结果；如果 Milvus 不可用，系统仍然可以靠 SQLite 检索工作。这能体现工程上的降级和可演进性，而不是把向量库变成单点依赖。

## Next Steps

等待用户确认后再进入下一步：联动与评测，补 Memory + Compression + RAG 的统一 benchmark 和面试材料同步。
