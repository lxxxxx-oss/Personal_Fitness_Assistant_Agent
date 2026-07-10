# 2026-07-10 Context Phase 4-5：compact 触发与可观测性

## 操作类型

功能增强 / Context Compression / 测试补充 / 文档同步

## 变更概述

按照 `docs/optimization/IMPLEMENTATION_SEQUENCE.md` 的第六步，完成 Context Phase 4-5 的最小闭环。

本次新增能力：

- 新增配置：
  - `COMPACT_TRIGGER_CHARS`，默认 6000
  - `MAX_PROMPT_CHARS`，默认 8192
- `PromptBuilder.attach()` 统一执行 compact 判断
- prompt 超过阈值时执行确定性压缩：
  - 保留 prompt 头部安全规则和任务说明
  - 注入 `_structured_state` 生成的 compact summary
  - 保留 prompt 尾部最近上下文和用户问题
  - 最终长度不超过 `MAX_PROMPT_CHARS`
- `_prompt_meta` 增加：
  - `original_chars`
  - `compact_triggered`
- `_structured_state` 增加：
  - `compact_summary`
  - `compact_triggered`
- `execution` 追加 compact 轨迹：
  - `component=compact`
  - `mode=deterministic`

## 当前边界

- 当前 compact 是确定性裁剪和结构化摘要，不调用 LLM 自动总结
- compact summary 只在当前运行态中使用，尚未写入 `summaries` 表
- 尚未做前端“已压缩”展示
- 尚未从 compact summary 中抽取长期记忆；后续如需抽取，必须走 Memory Writer 和 candidate confirmation
- 这是 prompt 超限保护和可观测性的最小闭环，不是生产级上下文管理系统

## 影响范围

- `app/config.py`
- `app/graph/prompt_builder.py`
- `tests/test_rag_context.py`

## 验收结果

见 `docs/tests/2026-07-10-context-phase4-5-compact-observability.md`。

## 面试口径

可以这样解释：

> 我没有一开始就让 LLM 自动总结长上下文，因为摘要质量不可控，还可能把隐私事实绕过确认写成长记忆。当前先做确定性 compact：超过阈值后保留安全规则和最近用户问题，中间用 `_structured_state` 生成可解释摘要，并在 `execution` 里公开 compact 事件。这样先保证 prompt 不超限、主链路不挂、压缩行为可观测，后续再升级为 LLM 摘要和前端展示。

## Next Steps

等待用户确认后再进入下一步：Memory Phase 6，Milvus 用户长期记忆语义增强。
