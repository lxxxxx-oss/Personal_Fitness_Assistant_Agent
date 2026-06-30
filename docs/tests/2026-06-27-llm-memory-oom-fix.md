# 2026-06-27 本地 LLM 内存安全测试

## 测试对象

- 进程级模型缓存。
- 并发首次加载锁。
- 加载失败后的缓存清理。
- SSE 流式接口单次最终生成。
- API 和集成回归。

## 测试命令

```powershell
$env:TAVILY_API_KEY=""
$env:MCP_SERVER_COMMAND="mock"
D:\Users\Lesedi\anaconda3\envs\fitness-agent\python.exe -m pytest tests/test_llm_loader.py tests/test_api.py -q
D:\Users\Lesedi\anaconda3\envs\fitness-agent\python.exe -m pytest tests/test_integration.py -q
```

## 当前结果

```text
tests/test_llm_loader.py + tests/test_api.py:
15 passed, 1 skipped

tests/test_integration.py:
6 passed

full pytest:
102 passed, 1 skipped, 2 warnings
```

## 覆盖内容

- 多个 `LLMLoader` 实例只调用一次模型加载。
- 8 个并发首次加载请求只创建一个模型对象。
- 模拟 `MemoryError` 后缓存保持为空，后续可重试。
- `/chat/stream` 不再调用一次 `generate()` 后再调用 `generate_stream()`。
- 普通 `/chat`、Motion API 和意图路由集成行为保持不变。

## 真实模型验证

使用本地 Qwen 模型创建两个 `LLMLoader`：

```text
first_ok=True
first_meta={"shared": false}
cache_entries=1

second_ok=True
second_meta={"shared": true}
cache_entries=1

same_model=True
same_tokenizer=True
```

说明第二个 loader 复用了同一份模型和 tokenizer，没有重复加载。

真实短生成结果：

```text
first_error=False
second_error=False
cache_entries=1
same_model=True
```

两次生成都完成，第二次未重复加载权重。

## 遗留风险

- 多 uvicorn worker 仍会按进程复制模型，因此本地模型必须单 worker。
- 当前共享模型生成采用串行锁，高并发吞吐有限。
- 尚未完成长时间压力测试和连续多用户请求的 Working Set 曲线记录。
- pytest 缓存目录存在 Windows 权限 warning，不影响测试断言。
