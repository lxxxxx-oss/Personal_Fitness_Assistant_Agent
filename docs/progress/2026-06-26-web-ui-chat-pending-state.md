# 2026-06-26 Web UI 对话等待状态优化

## 操作类型

用户体验修复 / MCP 稳定性优化 / 文档维护。

## 背景

用户手工测试真实 MCP 菜谱问题时，Web UI 在发送“番茄炒蛋怎么做”后只显示一个空的助手气泡。用户无法判断系统是在路由、调用 MCP、等待 LLM，还是已经卡死。

根因分两层：

- 前端在 `/chat/stream` 真正返回 token 前，只创建空消息气泡，没有可见状态文案。
- 后端 MCP Client 对 stdio JSON-RPC 响应使用阻塞 `readline()`，真实 MCP Server 如果没有及时响应，可能让整条链路长时间等待。

## 本次变更

更新代码：

- `app/static/index.html`
- `app/tools/mcp_client.py`

更新文档：

- `docs/README.md`
- `docs/progress/2026-06-26-web-ui-chat-pending-state.md`
- `docs/tests/2026-06-26-web-ui-chat-pending-state.md`

## 实现内容

- Web UI 发送消息后立刻显示“正在分析问题并准备调用合适的工具”。
- 收到 SSE `meta` 事件后，更新 intent badge，并显示“正在处理 {intent} 请求”。
- 收到第一个 token 后移除 pending 样式，展示真实回答。
- 流式失败时会 fallback 到 `/chat` 非流式接口。
- 流式和非流式都失败时，助手气泡显示明确错误说明，不再保留空白气泡。
- MCP Client 增加 `request_timeout_seconds`，默认 10 秒。
- MCP stdio JSON-RPC 读取响应时使用后台线程加 timeout，真实 MCP Server 不响应时会断开并返回可处理失败。

## 影响范围

- 不改变 `/chat`、`/chat/stream` 的协议。
- 不改变 Router 或 MCP 工具选择逻辑。
- Web UI 用户体验更清楚，尤其适合真实 MCP、LLM 推理或工具调用较慢的场景。
- MCP 真实 server 超时后仍会触发已有 fallback/错误处理链路，避免无限等待。

## Next Steps

1. 在浏览器手工验证 `/ui` 提问时 pending 状态可见。
2. 在真实 `howtocook-mcp` 环境中测试 MCP 菜谱问题。
3. 后续可以进一步让后端 SSE 在图执行前先发 `status` 事件，做到更细粒度的阶段提示。

## 2026-06-26 追加修复：Demo 回复固定番茄炒蛋

用户手工测试发现：在 `LLM_MOCK=1` 时，无论输入“番茄炒蛋怎么做”“番茄炒蛋要怎么做”还是“蛋炒饭怎么做”，Web UI 都会瞬间返回同一段番茄炒蛋回复。

根因：

- `LLM_MOCK=1` 会绕过真实本地模型，调用 `app.llm.loader._mock_response()`。
- MCP 子图的格式化 prompt 对所有菜谱都会包含“工具返回数据”“配料”等关键词。
- 旧版 `_mock_response()` 只要看到这些关键词，就固定返回番茄炒蛋 demo 文案。

修复：

- 新增 `_mock_recipe_response()`，从 MCP 工具返回 JSON 中解析 `name`、`ingredients`、`steps`、`recommendations` 和 `weeklyPlan`。
- demo 模式下根据工具返回 payload 生成对应菜谱回复，解析失败时才退回通用文本。
- 新增测试覆盖“蛋炒饭”不会被固定回答成“番茄炒蛋”。
