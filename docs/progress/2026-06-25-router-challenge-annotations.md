# Router Challenge Annotation Enhancement

## 目标

在不改变 Router 执行逻辑的前提下，增强 `data/eval/router_challenge_eval.jsonl` 的标注结构，让困难/失败样本不仅能说明“当前期望 intent 是什么”，还能说明：

- 主意图是什么。
- 次意图有哪些。
- 未来 multi-intent routing 可以按什么顺序执行。
- 当前 Router 为什么容易失败。

这一步服务于面试中的防守表达：当前 55.0% challenge accuracy 不是随意失败，而是有结构化标注的优化基线。

## 变更内容

文件：

- `data/eval/router_challenge_eval.jsonl`

每条样本新增字段：

```json
{
  "primary_intent": "motion",
  "secondary_intents": ["search"],
  "route_plan": ["motion", "search"],
  "expected_failure_reason": "当前规则容易被“查一下/最新”抢到 search，但用户明确先要求动作分析；后续需要识别顺序词“先/再”。"
}
```

字段含义：

- `primary_intent`：当前单 intent router 应该返回的主意图，和 `intent` 保持一致。
- `secondary_intents`：同一句话中存在的其他合理意图。
- `route_plan`：未来支持组合子图时的建议执行顺序。
- `expected_failure_reason`：当前规则/语义样例 router 为什么可能失败，或该样本保留的价值。

## 测试约束

文件：

- `tests/test_router_eval_script.py`

新增测试：

- `test_router_challenge_eval_has_multi_intent_annotations`

校验内容：

- `primary_intent == intent`
- `secondary_intents` 是 list
- `route_plan` 是非空 list
- `route_plan[0] == primary_intent`
- `expected_failure_reason` 是非空字符串

## 文档同步

已同步：

- `docs/README.md`
- `docs/interview/PROJECT_INTERVIEW_GUIDE.md`
- `docs/interview/SUBGRAPH_OPTIMIZATION_GUIDE.md`
- `docs/tests/2026-06-25-router-eval-and-challenge-test.md`
- `docs/progress/2026-06-25-router-challenge-eval.md`

## 面试说法

可以这样讲：

> Challenge set 不是普通错题集，我给每条困难样本都补了 primary intent、secondary intents、route plan 和 expected failure reason。这样后续要做 LLM classifier、embedding router 或 multi-intent routing 时，不是凭感觉改，而是能基于这些标注判断到底修复了哪些失败模式。

## 后续方向

1. 基于 `route_plan` 先写 multi-intent routing 设计文档。
2. 先用 mock LLM classifier 在 challenge set 上评估理论修正收益。
3. 再决定是否接真实 LLM classifier 或 embedding router。
