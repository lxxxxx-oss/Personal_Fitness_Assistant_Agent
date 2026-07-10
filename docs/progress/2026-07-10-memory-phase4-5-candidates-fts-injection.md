# 2026-07-10 Memory Phase 4-5：候选确认、FTS5 检索与预算注入

## 操作类型

功能增强 / API 变更 / Prompt 注入 / 测试补充 / 文档同步

## 变更概述

按照 `docs/optimization/IMPLEMENTATION_SEQUENCE.md` 的第五步，完成 Memory Phase 4-5 的最小闭环。

本次新增能力：

- SQLite 新增 `candidate_memories`
- SQLite 新增独立 FTS5 表：`memory_items_fts(memory_id UNINDEXED, content)`
- 新增候选记忆接口：
  - `GET /memory/candidates`
  - `POST /memory/candidates/{candidate_id}/confirm`
  - `POST /memory/candidates/{candidate_id}/reject`
- 新增长期记忆检索接口：
  - `GET /memory/search`
- 最小 Memory Writer 增加敏感拦截：
  - 普通显式“记住”直接进入 `memory_items`
  - 膝盖、旧伤、疼痛、疾病、过敏等健康/敏感内容先进入 `candidate_memories`
  - 用户确认后才进入正式长期记忆
- 长期记忆检索支持：
  - SQLite FTS5
  - 中文 LIKE 短片段兜底
  - importance + access_count 动态加权
- Prompt Builder 注入长期记忆：
  - Chat / Diet prompt 增加“长期记忆”段
  - 默认预算 1200 字符，超出后截断

## 当前边界

- 候选确认已有 API，但还没有 Web UI / 小程序确认入口
- FTS5 是关键词检索，不是 Milvus 语义检索
- 中文检索依赖 LIKE 短片段兜底，适合原型展示，不是生产级中文检索方案
- 长期记忆注入已有预算截断，但还没有全局 token 预算器
- 没有 memory access log 清理、删除同步、加密和用户授权

## 影响范围

- `app/memory/memory_store.py`
- `app/main.py`
- `app/graph/prompt_builder.py`
- `app/graph/state.py`
- `tests/test_memory_store.py`
- `tests/test_api.py`
- `tests/test_rag_context.py`
- `docs/API.md`
- `docs/README.md`

## 验收结果

见 `docs/tests/2026-07-10-memory-phase4-5-candidates-fts-injection.md`。

## 面试口径

可以这样解释：

> 我没有让所有长期事实直接入库。对普通偏好，比如“不喜欢香菜”，系统可以直接记；但对膝盖旧伤、过敏、疾病这类敏感信息，我先放进候选记忆，等用户确认后才进入正式长期记忆。检索上先用 SQLite FTS5 和中文 LIKE 兜底把链路打通，再把 top-k 长期记忆按预算注入 Prompt Builder。Milvus 用户记忆语义召回是下一阶段增强，不是当前主链路依赖。

## Next Steps

等待用户确认后再进入下一步：Context Phase 4-5，compact 触发、摘要/兜底提取和可观测事件。
