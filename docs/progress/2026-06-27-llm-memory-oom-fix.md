# 2026-06-27 本地 LLM 内存不足修复

## 操作类型

Bug 修复、资源管理重构。

## Bug 表现

运行本地模型时出现系统内存不足。问题具有高风险，因为进程可能被系统终止，且在多请求或流式调用时更容易复现。

## 根因分析

模型文件 `model.safetensors` 约 1.4 GB。当前 CPU 配置使用 `float32`，单份模型权重理论内存约 2.8 GB，尚未包含 tokenizer、临时张量和生成 KV cache。

原实现的问题：

1. 每个子图节点都会创建新的 `LLMLoader`。
2. 模型只缓存在 `LLMLoader` 实例内部，不同实例之间不共享。
3. Diet、Search、Motion、MCP 一次请求可能经过两个 LLM 节点，因此可能加载两份模型。
4. SSE/WebSocket 在 `graph.invoke()` 中先生成完整答案，随后又创建 loader 做第二次流式生成。
5. 并发首次请求没有加载锁，可能同时执行多次 `from_pretrained()`。

因此单进程内可能同时存在多份约 2.8 GB 的模型权重，并叠加生成缓存，最终触发 OOM。

## 修复方案

### 进程级共享模型缓存

在 `app/llm/loader.py` 中增加：

- `_MODEL_CACHE`
- `_MODEL_LOAD_LOCK`
- `_MODEL_GENERATION_LOCK`

缓存 key 由规范化模型路径、设备和 dtype 组成。不同 `LLMLoader` 实例保留各自生成参数，但共享底层 tokenizer/model。

### 并发首次加载保护

使用 double-checked locking：

- 先检查缓存。
- 获取加载锁后再次检查。
- 只有第一个请求执行 `from_pretrained()`。
- 加载失败后不写入缓存，并清理半初始化引用。

### 共享生成串行化

本地模型生成使用进程级生成锁，避免多个请求同时构建 KV cache。当前选择优先保证稳定性，而不是用并发换吞吐。

### 去除流式重复生成

SSE/WebSocket 状态增加 `_streaming=True`。

最终回答节点在流式模式下只写入 `_prompt`，不调用 `generate()`；流式层只执行一次 `generate_stream()`。

### 修正确定性生成参数

真实模型冒烟验证时发现 `generate()` 固定使用 `do_sample=True`，无法处理 `temperature=0`。现已调整为：

- `temperature > 0`：采样生成。
- `temperature = 0`：`do_sample=False`，使用 greedy decoding。

## 影响范围

- `app/llm/loader.py`
- `app/graph/state.py`
- `app/main.py`
- Chat、Diet、Search、Motion、MCP 的最终生成节点
- `tests/test_llm_loader.py`
- `tests/test_api.py`

接口请求和响应协议没有变化。

## 运行约束

- 本地模型使用单 uvicorn worker。
- 不要通过 `--workers 2` 等方式扩容；每个 worker 是独立进程，会各自加载一份模型。
- 需要并发推理时，应拆分独立模型服务并实施队列、批处理或显存/内存配额。

## 防御性改进

- 多 loader 共享模型的单元测试。
- 并发首次加载只分配一份模型的单元测试。
- 模型加载失败不污染共享缓存的单元测试。
- SSE 最终回答只生成一次的 API 测试。
- 日志区分首次加载和缓存复用。
- 真实 Qwen 权重完成两次短生成，第二次复用同一模型对象。

## Next Steps

1. 观察真实服务进程在首次请求和连续请求后的 Working Set。
2. 根据实际响应长度评估是否将默认 `MODEL_MAX_TOKENS` 从 1024 下调。
3. 如果需要多用户并发，将模型推理拆成独立服务，不在 FastAPI worker 内横向复制。

## 面试文档同步

已将该问题作为正式项目难点写入：

- `docs/interview/PROJECT_INTERVIEW_GUIDE.md` 的“项目难点：本地 LLM 的内存治理”。
- 高频问题 `Q12` 的补充回答。
- 高频问题 `Q12.1：为什么 0.6B 小模型也会导致内存不足？`。

面试口径覆盖问题现象、根因、解决方案、验证结果、工程取舍和生产化演进。
