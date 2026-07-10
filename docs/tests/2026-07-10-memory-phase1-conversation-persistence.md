# 2026-07-10 Memory Phase 1 会话持久化测试

## 测试目标

验证新增 SQLite 会话持久化不会破坏现有聊天、history、stream/WebSocket 契约，并确认 `conversation_id` 可创建和复用。

## 自动化测试

执行命令：

```powershell
pytest tests\test_conversation_store.py tests\test_api.py tests\test_integration.py tests\test_sliding_window.py -q
```

结果：

```text
40 passed, 1 warning
```

warning 来自 Starlette TestClient/httpx 兼容层弃用提示，与本次会话持久化无关。

## 覆盖内容

- `/chat` 返回合法响应和 `conversation_id`
- `/chat` 可复用传入的 `conversation_id`
- `/chat/stream` 仍逐 token 输出，并在 meta 中返回 metadata
- `/chat/ws` meta 中返回 `conversation_id`
- `/chat/{user_id}/history` 仍可读取最近会话历史
- `DELETE /chat/{user_id}/history` 仍可清空当前用户历史
- `SlidingWindowMemory` 原有行为不变

## 新增单元测试

新增 `tests/test_conversation_store.py`：

- 创建 conversation 并写入 user/assistant 消息
- 读取 messages 恢复顺序
- 归档用户 active conversation

## 遗留风险

- 当前测试尚未覆盖服务真实重启后的恢复流程，只覆盖了 `ConversationStore` 的持久化读写和 API 层行为。
- 当前 SQLite 持久化仍是本地原型级，没有多实例并发、认证授权、TTL 和隐私删除同步。
