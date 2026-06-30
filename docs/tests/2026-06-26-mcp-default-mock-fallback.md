# 2026-06-26 MCP 默认 mock 与 fallback 测试记录

## 测试对象

- `app/config.py`
- `app/graph/subgraphs/mcp.py`
- `app/tools/mcp_client.py`
- `tests/test_mcp_client.py`

## 测试命令

```bash
python -m pytest tests/test_mcp_client.py -q
```

## 测试内容

- 默认 `Config().mcp_server_command` 为 `mock`。
- 设置 `MCP_SERVER_COMMAND=howtocook-mcp` 后仍可切换真实 server 命令。
- MCP mock 模式工具发现和工具调用仍可用。
- 子图 fallback 测试已补充，但当前执行环境缺少 `langgraph`，因此该用例通过 `pytest.importorskip("langgraph")` 跳过，留待完整依赖环境执行。

## 测试结果

```text
13 passed, 1 skipped, 2 warnings
```

warning 来源：

```text
PytestCacheWarning: could not create cache path ... .pytest_cache ... Permission denied
```

该 warning 来自当前 Codex 工作区对 `.pytest_cache` 的权限限制，不影响本次 MCP 行为判断。

## 未执行项

尝试执行集成测试时，当前 shell 环境缺少 `fastapi`；尝试执行完整子图测试时，当前 shell 环境缺少 `langgraph`。需要在安装 `requirements.txt` 的 `fitness-agent` conda 环境中再跑：

```bash
python -m pytest tests/test_mcp_client.py tests/test_integration.py::TestIntegration::test_intent_routing_mcp -q
```
