# 2026-07-10 Memory Phase 1：会话持久化最小闭环

## 操作类型

功能新增 / API 变更 / 文档同步

## 变更概述

按照 `docs/optimization/IMPLEMENTATION_SEQUENCE.md` 的第一步，完成 Memory System Phase 1：

- 新增 `app/memory/conversation_store.py`
- 新增 `Config.memory_db_path`，默认 `data/memory/memory.db`
- SQLite 建表：
  - `conversations`
  - `messages`
  - `summaries`
  - `task_states`
- `/chat`、`/chat/stream`、`/chat/ws` 支持可选 `conversation_id`
- 响应和流式 meta 返回 `conversation_id`
- 不传 `conversation_id` 时复用该用户最近 active 会话，没有则创建新会话
- `SlidingWindowMemory` 继续作为 hot cache，进程重启后可从 SQLite 消息恢复
- `DELETE /chat/{user_id}/history` 会归档该用户 active conversations，并清理 hot cache

## 当前边界

这是会话持久化最小闭环，不是完整长期记忆系统：

- 尚未实现 `memory_items`、`MemoryWriter`、`candidate_memories`、FTS5 用户记忆检索
- SQLite 只作为本地原型持久化存储
- 当前仍无登录鉴权、用户授权、会话 TTL、多实例共享和加密/脱敏

## 影响范围

- `app/main.py`
- `app/config.py`
- `app/memory/conversation_store.py`
- `/chat`、`/chat/stream`、`/chat/ws`
- `/chat/{user_id}/history`

## 验收结果

见 `docs/tests/2026-07-10-memory-phase1-conversation-persistence.md`。

## Next Steps

等待用户确认后再进入下一步：Context Phase 1 Prompt Builder 统一入口，或按当前实施路线继续 Memory Phase 2 长期记忆基础表与 CRUD。

