# Router Challenge Eval

## 目标

在已有 66 条绿色 Router 回归集之外，新增一份困难/失败样本集，用于记录当前 Router 的真实边界。

这一步不是为了继续把总分堆到 100%，而是为了面试和后续优化时能说明：

- 当前规则 + 语义样例 Router 哪些场景已经稳定。
- 哪些场景仍然容易失败。
- 为什么后续需要 embedding router、LLM classifier 或 multi-intent route plan。

## 数据集分层

当前 Router eval 分成两层：

```text
data/eval/router_eval.jsonl
  -> 绿色回归集
  -> 当前 66 条
  -> 作为 CI/单测强约束，要求 100% 通过

data/eval/router_challenge_eval.jsonl
  -> 困难/失败样本集
  -> 当前 20 条
  -> 不使用 --fail-on-mismatch
  -> 用于暴露边界和评估后续优化收益
```

这样做比把所有样本都硬调到 100% 更适合面试：

- 不掩盖失败样本。
- 不夸大当前规则路由能力。
- 能清楚展示下一步优化依据。

## 新增样本类型

`router_challenge_eval.jsonl` 当前覆盖：

- `multi_intent_order`：一句话里有多个任务，且用户有明确顺序。
- `diet_vs_recipe`：饮食规划和具体菜谱之间的边界。
- `plan_vs_motion`：泛化训练计划和动作分析之间的边界。
- `freshness_authority`：带“最近/权威说法”的健康信息检索。
- `explicit_lookup`：显式查找和泛化训练建议之间的边界。
- `ambiguous_plan` / `ambiguous_progress`：跨饮食、训练、恢复的模糊问题。
- `tool_priority` / `file_plus_concept`：上传动作数据或文件信号的优先级。

当前每条 challenge case 已补充：

- `primary_intent`：当前单 intent router 应返回的主意图。
- `secondary_intents`：同一句话中存在但暂不作为主路由的次意图。
- `route_plan`：未来 multi-intent routing 可以采用的组合执行顺序。
- `expected_failure_reason`：为什么当前规则/语义样例 router 容易失败，或为什么该样本值得保留。

## 当前结果

绿色回归集：

```text
python scripts/eval_router.py --fail-on-mismatch
Total: 66 | Correct: 66 | Accuracy: 100.0%
```

困难/失败样本集：

```text
python scripts/eval_router.py --dataset data/eval/router_challenge_eval.jsonl
Total: 20 | Correct: 11 | Accuracy: 55.0%
```

当前 challenge set 暴露的主要失败：

- `motion -> search`：显式“查一下”会抢走用户先提出的动作分析任务。
- `chat -> search/diet/motion`：跨饮食、训练、恢复的模糊问题会被单一关键词或语义样例硬分流。
- `search -> diet/chat`：显式查找和“权威说法”还没有被充分建模。
- `mcp -> diet`：含食材和“安排一顿”的具体餐食请求容易被减脂词抢到 Diet。
- `diet -> mcp`：用户明确“不需要具体做法”时，当前规则还可能被“怎么做/早餐”类规则拉到 MCP。

## 面试说法

可以这样讲：

> 我把 Router eval 分成两层：第一层是绿色回归集，验证当前已承诺的路由行为不能回退；第二层是 challenge set，专门放当前规则路由容易失败的困难样本。这样不是为了包装 100% accuracy，而是为了诚实暴露边界，并给后续 embedding router、LLM classifier 和 multi-intent route plan 提供评估基线。

不要这样讲：

> Router 准确率已经 100%。

更准确的说法是：

> 当前绿色回归集是 66/66，但 challenge set 是 11/20。说明基础路由已经稳定，但复杂多意图、模糊计划和相近意图边界仍然需要下一阶段优化。

## 后续方向

1. 对 challenge set 中的低置信/模糊样本接入真实 LLM classifier 或 mock classifier，先评估修正收益。
2. 引入 embedding router，对比当前 char n-gram semantic examples 的收益。
3. 基于 `route_plan` 设计 multi-intent routing 的状态结构和执行策略。
4. 为每个 challenge category 建立更稳定的样本规模，避免单条样本代表整个类别。
