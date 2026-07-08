# 异步图与流式桥接验收

## 覆盖

- 慢速同步 `graph.invoke()` 运行时，asyncio 事件循环仍能继续调度。
- WebSocket 首 token 在同步生成器完成前发送。
- SSE 不重复执行最终生成，并通过 async token iterator 返回内容。
- 原有 HTTP、SSE、WebSocket metadata 与输入契约保持不变。

## 定向结果

```powershell
python -m pytest tests/test_api.py -q -p no:cacheprovider
```

结果：`26 passed, 1 warning`。

全量回归：`151 passed, 2 skipped, 1 warning`。
