# 2026-07-10 Memory Phase 2-3：长期记忆 CRUD 与最小 Memory Writer

## 操作类型

功能新增 / API 变更 / 测试补充 / 文档同步

## 变更概述

按照 `docs/optimization/IMPLEMENTATION_SEQUENCE.md` 的第四步，完成 Memory Phase 2-3 的最小闭环。

本次新增的是长期记忆基础能力：

- 新增 `app/memory/memory_store.py`
- 在本地 SQLite 中新增长期记忆表：
  - `memory_items`
  - `memory_sources`
  - `memory_relations`
- 新增 `MemoryStore`
- 新增长期记忆 CRUD 接口：
  - `GET /memory`
  - `POST /memory`
  - `GET /memory/{memory_id}`
  - `PATCH /memory/{memory_id}`
  - `DELETE /memory/{memory_id}`
- 删除采用逻辑删除：`status='deleted'`
- 实现 `memory_key = hash(user_id + kind + normalized_content)`，用于显式记忆去重
- 聊天链路增加最小 Memory Writer：
  - 用户明确说“请记住 / 帮我记住 / 记住一下 / 记住”时写入长期记忆
  - 来源标记为 `source_type='user_explicit_remember'`
  - 暂时通过规则推断 `goal / constraint / preference / note`

## 当前边界

这一步不是完整个性化记忆系统：

- 尚未实现候选记忆确认
- 尚未实现 FTS5 长期记忆检索
- 尚未实现长期记忆注入 Prompt Builder
- 尚未实现 Milvus 用户记忆语义召回
- 尚未实现隐私/健康信息的确认流
- 当前 `user_id` 仍不是登录身份，没有用户授权隔离

## 影响范围

- `app/memory/memory_store.py`
- `app/main.py`
- `tests/test_memory_store.py`
- `tests/test_api.py`
- `docs/API.md`
- `docs/README.md`

## 验收结果

见 `docs/tests/2026-07-10-memory-phase2-3-long-term-memory-writer.md`。

## 面试口径

可以这样解释：

> 我把短期会话历史和长期记忆拆开了。会话历史解决“最近聊到哪里”，长期记忆解决“用户明确希望系统长期记住什么”。这一阶段我没有让 LLM 自动猜用户记忆，而是先支持显式“记住……”和 CRUD，因为健身项目里身体状态、饮食偏好都涉及隐私，过早自动写入会带来误记和隐私风险。后续再做候选确认、FTS5 检索和 Milvus 语义增强。

## Next Steps

等待用户确认后再进入下一步：Memory Phase 4-5，候选记忆确认、FTS5 检索与分层预算注入。
