# Router Multi-intent Routing Design

## 目标

在不修改当前 Router 执行逻辑的前提下，先完成 multi-intent routing 的设计文档。

当前项目仍然保持单 intent 执行：

```text
intent -> one subgraph -> finalize
```

本阶段只定义后续如何从单 intent 演进到：

```text
primary_intent
secondary_intents
route_plan
```

## 新增文档

文件：

- `docs/interview/router/MULTI_INTENT_ROUTING_DESIGN.md`

文档内容包括：

- 为什么需要 multi-intent routing。
- `primary_intent`、`secondary_intents`、`route_plan`、`needs_clarification` 的字段定义。
- 建议新增的 RouterState 内部字段。
- 分阶段落地路线。
- Primary Intent Policy。
- Challenge Set 如何支撑设计。
- 面试表达和防守话术。

## 设计取舍

本阶段明确不直接串联多个子图，原因：

- 多子图串联会引入状态传递问题。
- 多子图结果需要合成。
- SSE/WebSocket 流式输出需要重新设计。
- 子图失败后的回退策略会更复杂。

因此推荐顺序是：

1. 先识别和记录多意图。
2. 继续只执行 `primary_intent` 对应子图。
3. 用 challenge set 评估 multi-intent 识别。
4. 再支持少数高价值组合，例如 `search -> diet`、`motion -> chat`。
5. 最后考虑组合结果合成。

## 文档同步

已同步：

- `docs/README.md`
- `docs/interview/PROJECT_INTERVIEW_GUIDE.md`
- `docs/interview/SUBGRAPH_OPTIMIZATION_GUIDE.md`

## 面试说法

可以这样讲：

> 当前执行链路仍然是单 intent，这是为了保持原型稳定。但我已经把 challenge set 标注成 multi-intent 结构，并单独写了 multi-intent routing 设计。后续会先让 Router 识别和记录 primary intent、secondary intents 和 route plan，再决定是否真的串联多个子图。这样不是为了炫复杂度，而是针对 challenge set 中已经暴露的多意图失败样本做演进。

不要声称项目已经完成了多意图子图串联执行。

当前真实状态是：

> 已完成 multi-intent 的评测标注和设计文档，执行层仍保持单 intent。

## 后续方向

1. 在 `RouterState` 中增加 `_primary_intent`、`_secondary_intents`、`_route_plan` 等内部字段。
2. 修改 Router，让它在保持 `intent = primary_intent` 的同时写入 multi-intent 调试字段。
3. 扩展 challenge set 测试，校验 Router 识别出的 route plan。
4. 再评估 LLM classifier 或 embedding router 对 challenge set 的提升。
