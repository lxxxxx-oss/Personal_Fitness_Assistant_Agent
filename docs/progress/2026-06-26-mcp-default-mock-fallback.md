# 2026-06-26 MCP 默认 mock 与真实 server fallback

## 操作类型

配置变更 / 工具链稳定性优化 / 测试补充 / 文档维护。

## 背景

项目原本支持 `MCP_SERVER_COMMAND=mock`，但 `app/config.py` 的默认值仍是 `howtocook-mcp`。如果用户直接启动后端，而本机没有安装真实 `howtocook-mcp`，MCP 菜谱子图会连接失败，影响开发和面试演示稳定性。

## 本次变更

更新代码：

- `app/config.py`
- `app/graph/subgraphs/mcp.py`
- `tests/test_mcp_client.py`

更新文档：

- `docs/README.md`
- `docs/interview/PROJECT_INTERVIEW_GUIDE.md`
- `docs/interview/SUBGRAPH_OPTIMIZATION_GUIDE.md`
- `docs/progress/2026-06-26-mcp-default-mock-fallback.md`
- `docs/tests/2026-06-26-mcp-default-mock-fallback.md`

## 实现内容

- 将 `mcp_server_command` 默认值改为 `mock`。
- 保留 `MCP_SERVER_COMMAND` 环境变量覆盖能力，可显式设置为 `howtocook-mcp` 或其他 MCP server 命令。
- MCP 子图连接真实 server 失败时，会自动 fallback 到 `MCPClient(server_command="mock")`。
- fallback 时在 state 中记录：
  - `_mcp_mode`
  - `_mcp_configured_command`
  - `_mcp_fallback_reason`
- 补充测试验证默认配置为 mock，以及环境变量仍可切换真实 server。

## 工具规范检查

- 职责清晰：`MCPClient` 仍只负责 MCP 连接、工具发现和工具调用；fallback 只发生在 MCP 子图初始化客户端时。
- 输入清晰：`MCP_SERVER_COMMAND` 仍是单一字符串配置，`mock` 是内置演示模式。
- 输出清晰：工具调用继续返回 `ToolResult`；子图内部 state 记录 fallback 元数据。
- 权限清晰：只有显式配置真实命令时才尝试启动外部 subprocess；默认 mock 不启动外部命令。
- 错误可处理：真实 MCP 不可用时降级为 mock，不让菜谱链路整体不可用。

## 影响范围

- 默认后端启动不再依赖 `howtocook-mcp`。
- 面试演示和两台电脑协作更稳定。
- 真实 MCP Server 仍可通过 `MCP_SERVER_COMMAND=howtocook-mcp` 启用。
- 不改变用户可见 API 协议。

## Next Steps

1. 在安装完整依赖的环境中跑全量 `pytest -q`。
2. 如果后续接真实 MCP Server，再补充真实 server 与 mock 数据一致性测试。
