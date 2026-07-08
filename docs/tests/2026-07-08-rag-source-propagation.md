# RAG 来源透传验收

## 覆盖

- 多个证据按 `[RefN]` 编号并包含来源标识。
- 重复知识来源在公共 metadata 中稳定去重。
- Chat 与 Diet 在流式模式生成 Prompt 时同步写入 `_sources`。

## 定向结果

```powershell
python -m pytest tests/test_rag_context.py tests/test_api.py::TestChatEndpoint -q -p no:cacheprovider
```

结果：`15 passed, 1 warning`。

全量回归：`150 passed, 2 skipped, 1 warning`。
