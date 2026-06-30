# Router 优化当前状态

本文档用于快速回答：Router 现在优化到哪一步了，下一步应该先做什么。

详细路线仍以 [../interview-archive/SUBGRAPH_OPTIMIZATION_GUIDE.md](../interview-archive/SUBGRAPH_OPTIMIZATION_GUIDE.md#6-router-和横切能力优化方向) 为准；多意图设计见 [MULTI_INTENT_ROUTING_DESIGN.md](./MULTI_INTENT_ROUTING_DESIGN.md)。

## 1. 一句话结论

Router 当前已经完成 Phase 1 至 Phase 4；本地 Qwen provider 已接入并完成 A/B，但默认关闭。Phase 4 已支持多意图观测、白名单组合执行和最终结果合成。

当前准确定位是：

```text
已落地：Weighted Rules + Deterministic Ambiguity Handling + Semantic Examples + Optional LLM Classifier
默认策略：真实 Qwen Router 关闭，保留 feature flag 和观测能力
当前能力：Phase 4 受控 multi-intent routing；不开放任意子图组合
```

## 2. 当前已落地能力

### Phase 1：Weighted Rule Router

已完成。

当前 Router 会扫描所有 intent 的规则并累加分数，而不是 first-match 命中即返回。

已落地内容：

- `WEIGHTED_RULES`
- `COMBO_RULES`
- `_apply_pattern_boosts()`
- `_route_scores`
- `_route_confidence`
- `_route_reason`
- `_route_source`
- `_route_matches`

价值：

- 路由行为可解释。
- 可以看到每个 intent 的分数和命中原因。
- 能用 eval 集做回归测试。

### Phase 2：Semantic Example Router

已完成轻量版本。

当前实现不是 embedding router，而是 char n-gram Jaccard 相似度，用来处理部分低置信、隐式表达样本。

已落地内容：

- `SEMANTIC_EXAMPLES`
- `_semantic_features()`
- `_semantic_route()`
- `data/eval/router_eval.jsonl`
- `scripts/eval_router.py`

当前绿色回归集：

```text
data/eval/router_eval.jsonl
66 cases
100.0% accuracy
```

### Phase 3：LLM Classifier Fallback

已完成工程契约、ambiguity detector、观测和真实本地 Qwen provider。

已落地内容：

- `_build_llm_router_prompt()`
- `_call_llm_router()`
- `_extract_json_object()`
- `_llm_classifier_route()`
- `LLM_ROUTER_MIN_CONFIDENCE = 0.70`
- `LLM_ROUTER_ENABLED` feature flag
- LLM contract outcomes、selection outcomes 和 latency metrics

当前边界：

- `_call_llm_router()` 已接共享 `LLMLoader`，默认由 feature flag 关闭。
- 开启时只对少数 review signals 调用模型。
- LLM 返回非法 JSON、非法 intent、低置信或 `needs_clarification=true` 时都会回退。
- 高置信规则场景中，LLM 只有置信度高于规则时才能覆盖。

所以现在不能说“已经实现 LLM Router”，准确说法是：

> Phase 3 已完成真实本地模型 A/B。由于准确率没有提升且单次分类平均约 6 秒，默认保持确定性 Router；LLM provider 作为可观测、可开关的实验能力保留。

## 3. 当前评测基线

### 绿色回归集

用途：保护当前已承诺的单 intent 行为。

```text
python scripts/eval_router.py --fail-on-mismatch

Total: 66
Correct: 66
Accuracy: 100.0%
```

这部分不应该为了优化 challenge set 被破坏。

### Challenge Set

用途：记录当前 Router 的困难边界和后续优化目标。

```text
python scripts/eval_router.py --dataset data/eval/router_challenge_eval.jsonl

Total: 36
Correct: 36
Accuracy: 100.0%
```

challenge set 已从 20 条扩充到 36 条。当前满分仍只是离线小样本结果，不能解释为生产泛化完成。

Phase 3 曾暴露并已纳入回归集的问题：

- 顺序词：`先 motion，再 search` 容易被 search 抢主意图。
- 否定约束：`不需要具体做法` 应抑制 `mcp`。
- plan-vs-motion：泛化训练计划不应误进 motion。
- diet-vs-recipe：饮食策略和具体菜谱容易互相抢。
- explicit lookup：`找一找`、`权威说法` 等检索信号还不够强。
- ambiguous plan：跨训练和饮食的综合问题更适合 chat 或澄清。

## 4. 现在到底卡在哪一步

不是卡在 Phase 1/2，它们已经完成。

当前真正的位置是：

```text
Phase 3 已完成
  -> 确定性 Router：绿色 66/66，challenge 36/36
  -> 本地 Qwen A/B：保持准确率但无净收益，默认关闭
  -> Phase 4 已完成：multi-intent 字段 + 四种白名单组合 + final synthesis
```

当前不再继续调 Phase 3 prompt，也不立即扩大组合范围。下一步应积累真实多意图请求的计划命中率、组合成功率和部分失败率，再决定是否扩充白名单。

## 5. Phase 3 A/B 结论

```text
LLM 关闭：green 66/66，challenge 36/36
LLM 开启：green 66/66，challenge 36/36
Challenge LLM calls：5
真正接管：1
平均调用延迟：约 6.22 秒
```

在加入“LLM 置信度必须高于规则”之前，本地 Qwen 曾把正确的 `mcp` 改成 `diet`。因此当前默认关闭是基于评测结果，而不是尚未实现。

## 6. 面试口径

可以这样讲：

> 当前 Router 已完成 Phase 4。绿色集主意图 66/66，challenge 的主意图、次意图和 route plan 都是 36/36。本地 Qwen classifier 做过真实 A/B，但没有净收益，因此默认关闭。多意图执行只开放四种两步白名单组合，并通过逐步结果记录、子图错误隔离和 final synthesis 保证可降级；其他组合继续走主意图单路由。
