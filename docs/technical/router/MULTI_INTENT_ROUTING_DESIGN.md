# Multi-intent Routing Design

本文档记录 Router 从单 intent 路由演进到受控 multi-intent routing 的设计与当前实现。

> 过渡说明：当前实现仍包含 `mcp`，但目标架构已经决定将菜谱请求并入 Diet 并删除该 intent。本文中的五意图样本属于当前实现证据，不代表后续四模块目标结构。

当前状态：

- Phase 4.1、4.2、4.3 已完成；简单请求仍走单子图，命中白名单的请求可走两个子图。
- `data/eval/router_eval.jsonl` 是绿色回归集，当前 66/66。
- `data/eval/router_challenge_eval.jsonl` 已扩充到 36 条；Phase 3 确定性 Router 当前为 36/36。
- 本地 Qwen classifier 已完成 A/B 但默认关闭；多意图识别使用确定性策略，不增加模型调用。
- challenge set 已补充 `primary_intent`、`secondary_intents`、`route_plan`、`expected_failure_reason`。

设计原则：

- 不为了炫技强行串联多个子图。
- 先识别和记录多意图，再逐步执行组合流程。
- 所有升级都要兼容当前单 intent Router。
- 多意图能力必须服务真实失败样本，而不是凭空增加复杂度。

## 1. 为什么需要 Multi-intent Routing

Router 对外仍返回一个兼容字段 `intent`，其值等于主意图：

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

状态：已完成。

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

状态：已完成。

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

状态：已完成。

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

当前实现只在多步计划中调用一次 final synthesis；单步计划不增加额外生成。流式接口收集各子图准备的上下文后，只执行一次最终流式生成。

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

> 当前 Router 已完成受控 multi-intent 演进：先记录 primary intent、secondary intents 和 route plan，再只对白名单中的四种两步组合串联执行，最后统一合成结果。简单请求和非白名单组合仍保持单路由，因此新增能力不会把整个图变成不可控的任意工作流。

如果面试官问“为什么现在不直接执行多个子图”：

> 我没有开放任意子图组合，而是只支持 `search -> diet`、`search -> chat`、`motion -> chat`、`motion -> diet`。每步结果单独记录，部分失败时保留成功结果，SSE/WebSocket 最终只生成一次。这样既解决真实的跨任务请求，也把状态传递和错误范围控制在可测试的边界内。

## 8. 后续实现建议

后续建议：

1. 记录真实流量中的 route plan 命中率、组合成功率和部分失败率。
2. 为四种组合补充更大的端到端评测集，而不是只依赖 36 条 challenge set。
3. 只有在样本证明有价值时才扩充白名单或考虑三步计划。
4. 继续保持真实 LLM classifier 默认关闭，除非更强模型在 A/B 中带来净收益。
