# 同步 LangGraph 与流式生成异步桥接

## 问题

- FastAPI 的 `/chat`、SSE 和 WebSocket 都在 async handler 中直接调用同步 `graph.invoke()`。
- WebSocket 已把最终 token 生成放入线程，但 graph 准备阶段仍可能执行 Diet 画像、Search query rewrite 或 Motion think 等同步模型调用。
- SSE 直接在事件循环中迭代同步 `generate_stream()`，逐 token 生成期间会阻塞其他异步 I/O。

## 修复

- 新增 `_invoke_graph()`，统一通过 `asyncio.to_thread()` 执行同步 LangGraph。
- 抽取 `_iterate_llm_tokens()`：生产线程读取同步生成器，通过 thread-safe queue 投递到 asyncio，暴露 async iterator。
- SSE 和 WebSocket 共用 token 桥接；WebSocket helper 只保留协议发送与回复拼接职责。

## 边界

- 此修改释放事件循环，不让模型计算占住 asyncio 主线程。
- `LLMLoader` 的共享生成锁仍让同进程模型推理串行；这是内存安全取舍，不应表述为并行推理。
- 生产化仍应把模型拆为独立推理服务，并增加队列、超时和并发治理。
