# 执行模式可见性专项验证

## 验证范围

- 浮点与布尔环境变量解析。
- HTTP、SSE、WebSocket 的 `execution` 输出结构。
- Search mock、MCP fallback 的降级轨迹。
- 小程序 execution 数据传递和组件脚本语法。

## 定向命令

```powershell
python -m py_compile app/config.py app/main.py app/graph/state.py app/graph/router.py app/graph/subgraphs/*.py
python -m pytest tests/test_config.py tests/test_api.py::TestChatEndpoint tests/test_search_tool.py tests/test_mcp_client.py -q -p no:cacheprovider
node --check miniprogram/pages/chat/chat.js
node --check miniprogram/components/message-bubble/message-bubble.js
```

## 当前结果

- 定向自动化测试：`28 passed, 1 warning`。
- 全量自动化回归：`129 passed, 2 skipped, 1 warning`。
- Python 编译与 JavaScript 语法检查通过。
- warning 为既有 Starlette TestClient/httpx 兼容层弃用提示。

## 待验收

- 微信开发者工具中的标签颜色、换行和长 mode 展示。
- 真实 Tavily、Milvus、MCP Server 场景下的 mode 对照。
- 组合路由在真实依赖混合状态下的多标签展示。
