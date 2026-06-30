# 2026-06-30 Router Phase 4 实施记录

## 操作类型

Router 多意图识别、受控组合执行与结果合成。

## 实施边界

Phase 4 按三个检查点推进：

1. Phase 4.1：识别并记录多意图，不改变主意图兼容语义。
2. Phase 4.2：只执行白名单中的两步组合流程，其他计划降级为主意图单路由。
3. Phase 4.3：汇总各子图结果，兼容非流式与流式最终回答。

## Checkpoint 1：Phase 4.1 多意图观测

状态：已完成。

已落地：

- `RouteDecision` 新增 `primary_intent`、`secondary_intents`、`route_plan`、`multi_intent_reason`、`needs_clarification`。
- `RouterState` 新增对应内部调试字段。
- `intent` 始终等于 `primary_intent`，现有 API 响应保持兼容。
- 次意图识别使用确定性分句、规则分数和领域边界策略，不额外调用 LLM。
- 明确顺序词才产生多步骤 `route_plan`；仅观察到相关领域时只记录 secondary intent。
- 跨训练/饮食且信息不足的计划记录 `needs_clarification=true`，不盲目串联。
- Router eval 新增 secondary intent 与 route plan 精确匹配指标。

阶段验证：

```text
tests/test_router.py + tests/test_router_eval_script.py: 34 passed
challenge primary intent: 36/36
challenge secondary intent exact: 36/36
challenge route plan exact: 36/36
```

## Checkpoint 2：Phase 4.2 受控组合执行

状态：已完成。

执行白名单：

```text
search -> diet
search -> chat
motion -> chat
motion -> diet
```

执行约束：

- 只执行恰好命中白名单的两步计划。
- 非白名单计划只执行主意图，并记录 `unsupported_route_plan`。
- `needs_clarification=true` 时只执行主意图。
- 每步输出记录在 `_route_results`，包含 intent、result、error、prompt 和 sources。
- 顶层安全边界捕获子图异常；组合流程可以保留其他已成功步骤。

实现过程中发现 Search 在外网失败且 `ToolResult.data=None` 时调用 `len(None)`，导致 `/chat` 返回 500。现已将失败结果统一为空列表，并记录 `search_degraded`，同时补充顶层子图异常隔离。

## Checkpoint 3：Phase 4.3 结果合成

状态：已完成。

- 单步计划保持原结果和 Prompt，不额外调用合成模型。
- 多步非流式请求将各步骤结果交给一次 final synthesis。
- 多步流式请求收集各子图准备的上下文，最终只流式生成一次。
- 部分失败时基于成功结果合成并明确边界。
- 全部失败时返回结构化错误文本。
- 合成模型失败时退回按 intent 标记的子结果，不丢失已完成工作。

阶段验证：

```text
Router + API + integration: 55 passed, 1 warning
full pytest: 114 passed, 1 skipped, 1 warning
green router eval: 66/66
challenge primary/secondary/route-plan exact: 36/36
```

warning 来自 Starlette TestClient 对 httpx 兼容层的弃用提示，与 Phase 4 行为无关。

## 工具/函数接口规范检查

Phase 4 总体结论：通过。

- 职责清晰：识别、执行推进、结果收集和最终合成分别由独立节点负责。
- 输入清晰：执行器只接收 Router 生成且通过白名单检查的计划。
- 输出清晰：每步结果结构固定，最终恢复 `intent=primary_intent`。
- 权限清晰：纯内存计算，不访问网络、不写外部数据。
- 错误可处理：不支持的组合、澄清请求、子图失败和合成失败均有独立降级路径。
