# 2026-06-26 Web UI 对话等待状态测试记录

## 测试对象

- `app/static/index.html`
- `app/tools/mcp_client.py`
- `tests/test_mcp_client.py`

## 测试命令

前端脚本语法检查：

```bash
node --check tmp-ui-script.js
```

后端 MCP 客户端语法检查：

```bash
python -m py_compile app/tools/mcp_client.py
```

MCP 单元测试：

```bash
python -m pytest tests/test_mcp_client.py -q
```

LLM demo 菜谱回复测试：

```bash
python -m pytest tests/test_llm_loader.py -q
```

## 测试结果

```text
node --check: passed
py_compile: passed
13 passed, 1 skipped, 2 warnings
2 passed, 1 skipped, 2 warnings
```

warning 来源：

```text
PytestCacheWarning: could not create cache path ... .pytest_cache ... Permission denied
```

该 warning 来自当前 Codex 工作区对 `.pytest_cache` 的权限限制，不影响本次判断。

## 未完成验证

当前尚未完成浏览器端真实点击验收。建议用户启动后端后访问：

```text
http://127.0.0.1:<port>/ui
```

输入：

```text
番茄炒蛋怎么做？
```

预期：

- 用户消息立即显示。
- 助手气泡立即显示 pending 状态。
- intent meta 到达后高亮 MCP。
- 如果真实 MCP 或 LLM 较慢，页面仍显示明确状态，不再空白等待。
- 在 `LLM_MOCK=1` 下，不同 MCP 菜谱 payload 应返回对应菜名，不应一律返回番茄炒蛋。
