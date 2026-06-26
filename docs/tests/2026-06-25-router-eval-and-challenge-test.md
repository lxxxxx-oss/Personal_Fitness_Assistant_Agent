# Router Eval and Challenge Test

## 测试时间

2026-06-25

## 测试目标

验证 Router 优化后的两类评测集和全量自动化测试是否符合当前项目状态。

本次测试不是只记录一个总分，而是区分：

- 绿色回归集：验证当前已经承诺的路由行为不能退化。
- 困难/失败样本集：记录当前 Router 的真实边界，作为后续优化基线。
- 全量 pytest：确认新增数据集、评测脚本和文档相关代码改动没有破坏现有功能。

## 测试范围

涉及文件：

- `app/graph/router.py`
- `scripts/eval_router.py`
- `data/eval/router_eval.jsonl`
- `data/eval/router_challenge_eval.jsonl`
- `tests/test_router.py`
- `tests/test_router_eval_script.py`

## 1. Router 绿色回归集

命令：

```bash
python scripts/eval_router.py --fail-on-mismatch
```

测试内容：

- 读取 `data/eval/router_eval.jsonl`。
- 覆盖当前已承诺的 66 条 Router 行为。
- 验证 `chat/search/diet/motion/mcp` 五类 intent 是否全部符合标注。
- 输出 per-intent precision/recall/F1。
- 输出 evaluation slices、route source counts 和 confusion matrix。
- 因为使用 `--fail-on-mismatch`，如果有任何误分类，命令会失败。

真实结果：

```text
Total: 66 | Correct: 66 | Accuracy: 100.0%

chat     support=18 precision=100.0% recall=100.0% f1=100.0%
diet     support=12 precision=100.0% recall=100.0% f1=100.0%
mcp      support=9  precision=100.0% recall=100.0% f1=100.0%
motion   support=14 precision=100.0% recall=100.0% f1=100.0%
search   support=13 precision=100.0% recall=100.0% f1=100.0%
```

Evaluation slices：

```text
boundary_concept          2/2
boundary_training_plan    3/3
fallback_unclear          3/3
freshness_search          3/3
implicit_intent           6/6
low_confidence            1/1
multi_intent_primary      4/4
recipe_tool               3/3
tool_file_signal          2/2
uncategorized            39/39
```

Route source counts：

```text
fallback             4
semantic_examples    6
weighted_rules       56
```

结论：

绿色回归集全部通过。当前 Router 对已承诺样本的行为稳定，没有出现回归。

## 2. Router 困难/失败样本集

命令：

```bash
python scripts/eval_router.py --dataset data/eval/router_challenge_eval.jsonl
```

测试内容：

- 读取 `data/eval/router_challenge_eval.jsonl`。
- 覆盖 20 条专门设计的困难样本。
- 重点观察当前规则路由在复杂边界上的失败模式。
- 不使用 `--fail-on-mismatch`，因为该数据集不是 CI 强制通过集，而是后续优化基线。
- 每条样本都补充 `primary_intent`、`secondary_intents`、`route_plan` 和 `expected_failure_reason`，用于说明主意图、次意图、未来组合执行顺序和当前失败原因。

真实结果：

```text
Total: 20 | Correct: 11 | Accuracy: 55.0%
```

Per-intent metrics：

```text
chat     support=4 predicted=1 precision=0.0%  recall=0.0%  f1=0.0%
diet     support=5 predicted=7 precision=57.1% recall=80.0% f1=66.7%
mcp      support=2 predicted=2 precision=50.0% recall=50.0% f1=50.0%
motion   support=5 predicted=6 precision=66.7% recall=80.0% f1=72.7%
search   support=4 predicted=4 precision=50.0% recall=50.0% f1=50.0%
```

Evaluation slices：

```text
ambiguous_plan           0/1
ambiguous_progress       0/1
diet_vs_recipe           2/3
explicit_lookup          0/1
file_plus_concept        1/1
freshness_authority      0/1
freshness_search         1/1
implicit_diet            1/1
implicit_motion          1/1
motion_vs_health_advice  1/1
multi_intent_order       0/1
multi_intent_search      1/1
multi_intent_secondary   1/1
multi_step_chat          0/1
plan_vs_motion           0/1
recipe_tool              1/2
tool_priority            1/1
```

主要失败样本：

```text
motion -> search:
先帮我分析深蹲动作，再查一下最新的纠正方法

chat -> search:
能不能根据我最近训练状态安排一下吃和练

search -> diet:
最近有什么关于蛋白质摄入和肾脏健康的权威说法

mcp -> diet:
帮我用冰箱里的鸡蛋和青菜安排一顿减脂餐

chat -> motion:
我想改善圆肩，应该练什么动作

chat -> diet:
我最近体重没变，是不是训练没效果

search -> chat:
帮我找一找适合新手的无器械训练计划

diet -> mcp:
给我一个高蛋白早餐方案，不需要具体做法

chat -> motion:
我想学会硬拉，先讲原理再看动作
```

结论：

困难集准确率为 55.0%。这不是失败，而是当前阶段有意保留的边界记录，用来说明：

- 基础 Router 已经稳定。
- 复杂多意图、模糊计划、显式查找、饮食和菜谱边界仍然需要后续优化。
- 下一步优化可以围绕 multi-intent route plan、embedding router 或真实 LLM classifier 展开。

## 3. 全量自动化测试

命令：

```bash
python -m pytest -q
```

测试内容：

- API 基础行为。
- Router 单元测试。
- Router eval 脚本加载和评估。
- Retriever、工具层、MCP、Motion、流式接口等已有测试。
- 新增 challenge eval 数据集加载测试。

真实结果：

```text
78 passed, 1 skipped, 1 warning in 3.66s
```

warning：

```text
StarletteDeprecationWarning:
Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
```

结论：

全量自动化测试通过。当前 warning 来自 Starlette/FastAPI 测试依赖版本提示，不是本次 Router eval 改动引入的功能失败。

新增结构校验：

- `tests/test_router_eval_script.py` 会校验 challenge set 的多意图标注字段。
- 校验内容包括 `primary_intent == intent`、`secondary_intents` 为列表、`route_plan` 非空且以 `primary_intent` 开头、`expected_failure_reason` 非空。

## 总结

当前真实状态应表述为：

> Router 绿色回归集为 66/66，说明已承诺样本稳定；challenge set 为 11/20，说明复杂多意图、模糊计划和相近意图边界仍有明确优化空间；全量测试为 78 passed, 1 skipped, 1 warning。

面试中不要只说“Router 准确率 100%”。更准确的说法是：

> 我把 Router eval 分成绿色回归集和 challenge set。绿色回归集用于防止已知行为退化，challenge set 用于记录当前失败样本和后续优化方向。这样比单纯包装一个 100% accuracy 更诚实，也更工程化。
