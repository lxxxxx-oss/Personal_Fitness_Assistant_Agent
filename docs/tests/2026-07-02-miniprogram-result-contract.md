# 小程序回答元数据专项验证

## 验证对象

- `/chat` 的 `sources`、`warnings` 返回与去重。
- `/chat/stream` 的 meta 事件字段。
- `/chat/ws` 的 meta 消息字段。
- 小程序聊天页和消息气泡脚本语法。

## 自动化命令

```powershell
python -m py_compile app/main.py
python -m pytest tests/test_api.py::TestChatEndpoint -q -p no:cacheprovider
node --check miniprogram/pages/chat/chat.js
node --check miniprogram/components/message-bubble/message-bubble.js
node --check miniprogram/utils/api.js
```

## 当前结果

- API 定向测试：`6 passed, 1 warning`。
- 全量自动化回归：`124 passed, 2 skipped, 1 warning`。
- JavaScript 语法检查：全部通过。
- warning 为既有 Starlette TestClient/httpx 兼容层弃用提示，不影响接口行为。

## 遗留验证

- 微信开发者工具中的视觉布局和滚动行为。
- 真机 WebSocket、HTTPS 合法域名和弱网降级。
- 来源 URL 的复制或打开交互。
