# Multi-intent Routing Design

本文档记录 Router 后续从单 intent 路由演进到 multi-intent routing 的设计方案。

当前状态：

- 生产执行链路仍然是单 intent：`intent -> one subgraph -> finalize`。
- `data/eval/router_eval.jsonl` 是绿色回归集，当前 66/66。
- `data/eval/router_challenge_eval.jsonl` 是困难/失败样本集，当前 20 条，11/20。
- challenge set 已补充 `primary_intent`、`secondary_intents`、`route_plan`、`expected_failure_reason`。

设计原则：

- 不为了炫技强行串联多个子图。
- 先识别和记录多意图，再逐步执行组合流程。
- 所有升级都要兼容当前单 intent Router。
- 多意图能力必须服务真实失败样本，而不是凭空增加复杂度。

## 1. 为什么需要 Multi-intent Routing

当前 Router 只能返回一个 intent：

```text
chat | search | diet | motion | mcp
```

这对大部分简单请求足够，例如：

```text
查一下最新增肌研究 -> search
帮我看看深蹲姿势 -> motion
减脂期间怎么吃 -> diet
番茄炒蛋怎么做 -> mcp
什么是渐进超负荷 -> chat
```

但用户真实问题经常同时包含多个任务：

```text
先帮我分析深蹲动作，再查一下最新的纠正方法
```

这里至少包含：

- `motion`：先分析深蹲动作。
- `search`：再查最新纠正方法。

如果当前单 intent Router 只返回 `search`，就会忽略用户明确写在前面的动作分析任务。

因此 multi-intent routing 的价值不是“让系统更复杂”，而是解决单 intent 路由在多任务输入上的信息丢失问题。

## 2. 核心字段定义

后续 Router 可以从单字段：

```json
{
  "intent": "motion"
}
```

扩展为：

```json
{
  "primary_intent": "motion",
  "secondary_intents": ["search"],
  "route_plan": ["motion", "search"],
  "needs_clarification": false,
  "reason": "用户先要求动作分析，再要求查找最新纠正方法"
}
```

字段含义：

- `primary_intent`：本轮最应该优先执行的主任务。
- `secondary_intents`：同一句话里存在但不是第一优先级的任务。
- `route_plan`：未来支持组合执行时的建议子图顺序。
- `needs_clarification`：问题过于模糊或信息不足时，不直接硬路由。
- `reason`：用于日志、调试和面试解释。

兼容策略：

- 当前 `intent` 仍然等于 `primary_intent`。
- 现有 API 和子图仍然只依赖 `intent`。
- 新字段先写入 RouterState 的内部调试字段，不改变用户响应协议。

## 3. 建议新增 RouterState 字段

未来可以在 `RouterState` 中增加：

```python
_primary_intent: str
_secondary_intents: list[str]
_route_plan: list[str]
_multi_intent_reason: str
_needs_clarification: bool
```

说明：

- `_primary_intent` 与当前 `intent` 保持一致。
- `_secondary_intents` 只用于观测和后续组合执行。
- `_route_plan` 第一阶段只记录，不执行。
- `_needs_clarification` 用于避免对模糊请求硬分流。

## 4. 分阶段落地路线

### Phase 4.1：只识别和记录，不执行组合子图

目标：

- 保持现有单 intent 执行逻辑不变。
- Router 输出 `primary_intent`、`secondary_intents`、`route_plan`。
- `intent = primary_intent`，仍然只执行一个子图。
- 用 challenge set 评估多意图识别是否正确。

适合先落地，因为风险低：

- 不改子图之间的数据流。
- 不处理多个子图结果合成。
- 不影响 SSE/WebSocket 流式输出。
- 仍能支撑面试讲解和后续评测。

### Phase 4.2：支持有限组合流程

只支持少量高价值组合：

```text
search -> diet
search -> chat
motion -> chat
motion -> diet
```

示例：

```text
我想减脂，顺便查一下最近间歇性禁食的研究
route_plan = ["search", "diet"]
```

执行策略：

1. 先执行 `search` 获取最新资料。
2. 将搜索结果摘要写入 state。
3. 再执行 `diet`，让饮食建议参考搜索结果。

注意：

- 不建议一开始支持任意子图组合。
- 每个组合都要有明确的状态输入和输出约定。
- 如果任一子图失败，需要有降级策略。

### Phase 4.3：组合结果合成

当多个子图都执行后，需要一个 final synthesis 节点：

```text
route_plan execution results
  -> merge evidence/results
  -> final synthesis
```

这一步会影响：

- 最终回答格式。
- 流式输出。
- 错误处理。
- 多来源引用。
- 子图之间状态边界。

因此建议放到后期，不作为当前面试原型的必做项。

## 5. Primary Intent Policy

当前 challenge set 中已经使用以下策略：

```text
显式搜索 / 最新研究 / 查找资料 -> search
动作文件 / 姿势判断 / 技术问题 -> motion
具体菜谱 / 食材做法 / 晚餐菜 -> mcp
个人饮食规划 / 摄入量 / 减脂增肌饮食 -> diet
泛化训练建议 / 概念解释 / 不明确表达 -> chat
```

多意图时进一步考虑：

- 有顺序词：优先遵守用户顺序，例如“先 motion，再 search”。
- 有强工具信号：`.npz`、上传动作数据优先 motion。
- 有时效性信号：最新、最近、研究、权威说法优先 search。
- 有否定约束：例如“不需要具体做法”应抑制 mcp。
- 信息不足：优先 chat 或 clarification，而不是硬分流。

## 6. Challenge Set 如何支撑设计

`router_challenge_eval.jsonl` 已经包含：

```json
{
  "text": "先帮我分析深蹲动作，再查一下最新的纠正方法",
  "intent": "motion",
  "primary_intent": "motion",
  "secondary_intents": ["search"],
  "route_plan": ["motion", "search"],
  "category": "multi_intent_order",
  "expected_failure_reason": "当前规则容易被“查一下/最新”抢到 search，但用户明确先要求动作分析；后续需要识别顺序词“先/再”。"
}
```

这类样本可以用于评估：

- 当前单 intent 是否选对 `primary_intent`。
- 未来 multi-intent router 是否识别出 `secondary_intents`。
- 未来 route planner 是否生成正确的 `route_plan`。
- LLM classifier 或 embedding router 是否真的改善困难样本。

## 7. 面试表达

可以这样讲：

> 当前项目执行链路仍然是单 intent，这是为了保持系统稳定。但我已经把 challenge set 标注成 multi-intent 结构，包括 primary intent、secondary intents 和 route plan。这样后续不是盲目改 Router，而是可以基于这些困难样本逐步评估：先识别多意图，再记录 route plan，最后再考虑串联执行多个子图。

如果面试官问“为什么现在不直接执行多个子图”：

> 多子图串联会引入状态传递、结果合成、流式输出和错误回退等复杂度。当前作为面试原型，我先把多意图识别和评测基线做好，执行层仍保持单 intent。这样既能说明演进方向，也不会为了炫技把系统做得不稳定。

## 8. 后续实现建议

推荐下一步：

1. 在 RouterState 中增加 multi-intent 调试字段。
2. 修改 Router，让它在不改变 `intent` 的情况下写入 `_primary_intent`、`_secondary_intents`、`_route_plan`。
3. 增加 challenge set 的 multi-intent 识别测试。
4. 先用 mock LLM classifier 评估 challenge set 的理论修正收益。
5. 再决定是否接真实 LLM classifier 或 embedding router。
