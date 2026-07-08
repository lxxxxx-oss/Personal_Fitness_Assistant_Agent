# API 输入边界验收

## 覆盖范围

- `/motion/analyze-image` 在后端分块读取期间强制执行图片大小上限。
- `/chat/ws` 对空字段、超长字段和错误类型返回 `INVALID_REQUEST`。
- HTTP、SSE 与 WebSocket 共享 `ChatRequest` 的 1-64 / 1-4096 字段边界。

## 执行结果

```powershell
python -m pytest tests/test_api.py -q -p no:cacheprovider
```

结果：`25 passed, 1 warning`。

```powershell
python -m pytest -q -p no:cacheprovider
```

结果：`145 passed, 2 skipped, 1 warning`。

warning 来自 Starlette TestClient/httpx 兼容层弃用提示。两个 skip 分别属于需要本地真实模型和显式 Milvus 服务配置的可选测试。
