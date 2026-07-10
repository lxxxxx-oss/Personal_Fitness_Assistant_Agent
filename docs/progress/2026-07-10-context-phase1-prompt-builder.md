# 2026-07-10 Context Phase 1：Prompt Builder 统一入口

## 操作类型

代码重构 / Context Compression 前置能力 / 文档同步

## 变更概述

按照 `docs/optimization/IMPLEMENTATION_SEQUENCE.md` 的第二步，完成 Context Phase 1：统一 Prompt Builder 入口。

本次没有引入自动摘要、上下文压缩或长期记忆注入，只做一个稳定前置层：

- 新增 `app/graph/prompt_builder.py`
- 将 Chat / Diet / Search / MCP 的主要文本 prompt 拼接迁移到 `PromptBuilder`
- 为生成型 prompt 写入 `_prompt_meta`
  - `kind`：prompt 类型，如 `chat.answer`
  - `chars`：prompt 字符数
  - `sections`：当前 prompt 使用了哪些上下文段
- `RouterState` 补充 `_prompt_meta`
- 保留原有 `SlidingWindowMemory`、RAG source 透传、SSE/WebSocket 流式逻辑

## 当前边界

这一步只是让 prompt 结构“可控、可观测、可扩展”，还不是完整 Context Compression：

- 尚未实现 `_structured_state`
- 尚未实现工具结果 preview 的统一裁剪
- 尚未实现 compact 触发、摘要生成或结构化提取
- 尚未把长期记忆 top-k 注入到统一 prompt 预算中
- Motion 的姿态分析 prompt 暂未纳入本阶段，因为它与图片/视频分析结果和动作指标强绑定，更适合在后续工具 preview 阶段统一处理

## 影响范围

- `app/graph/prompt_builder.py`
- `app/graph/state.py`
- `app/graph/subgraphs/chat.py`
- `app/graph/subgraphs/diet.py`
- `app/graph/subgraphs/search.py`
- `app/graph/subgraphs/mcp.py`
- `tests/test_rag_context.py`

## 验收结果

见 `docs/tests/2026-07-10-context-phase1-prompt-builder.md`。

## 面试口径

可以这样解释：

> 我没有一上来就做 LLM 自动摘要，因为那样很容易把重要信息压丢，而且不可控。我的第一步是把各个子图分散的 prompt 拼接收束成统一 Prompt Builder，并记录 prompt 类型、长度和上下文段来源。这样后续做压缩、长期记忆注入、工具结果裁剪时，都有一个统一入口和可测试指标。

## Next Steps

等待用户确认后再进入下一步：Context Phase 2-3，增加 `_structured_state` 和工具结果 preview。
