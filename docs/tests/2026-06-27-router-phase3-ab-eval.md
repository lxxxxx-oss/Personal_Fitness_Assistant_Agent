# 2026-06-27 Router Phase 3 A/B 评测

## 测试对象

- 确定性边界规则。
- Ambiguity detector 和触发观测。
- 本地 Qwen3-0.6B classifier provider。
- LLM 接管置信度保护。
- 绿色回归集和扩充 challenge set。

## 数据集

- `data/eval/router_eval.jsonl`：66 条绿色回归样本。
- `data/eval/router_challenge_eval.jsonl`：从 20 条扩充到 36 条困难样本。

新增困难样本覆盖：

- 顺序词变体。
- 否定约束变体。
- 权威资料检索。
- plan-vs-motion。
- diet-vs-recipe。
- 食材构造一餐。
- 进展诊断和跨域计划。

## 关闭 LLM 基线

```powershell
$env:LLM_ROUTER_ENABLED="0"
python scripts/eval_router.py --fail-on-mismatch
python scripts/eval_router.py --dataset data/eval/router_challenge_eval.jsonl
```

结果：

```text
green: 66/66, 100.0%
challenge: 36/36, 100.0%
challenge review attempts: 5, outcome=unavailable
```

## 开启本地 Qwen A/B

```powershell
$env:LLM_ROUTER_ENABLED="1"
$env:LLM_ROUTER_MAX_TOKENS="128"
python scripts/eval_router.py --fail-on-mismatch
python scripts/eval_router.py --dataset data/eval/router_challenge_eval.jsonl
```

最终结果：

```text
green: 66/66, 100.0%
green calls: 5
green selected: 4
green rejected_not_higher_confidence: 1
green average latency: 6091.94 ms

challenge: 36/36, 100.0%
challenge calls: 5
challenge selected: 1
challenge rejected_not_higher_confidence: 4
challenge average latency: 6221.92 ms
```

在增加置信度保护之前，开启模型时 challenge 曾降到 35/36：

```text
减脂晚餐具体怎么做
expected=mcp
LLM predicted=diet
```

因此新增保护：高置信规则场景中，LLM confidence 必须高于 rule confidence 才能接管。

## 自动化测试

```text
tests/test_router.py + tests/test_router_eval_script.py:
31 passed

full pytest:
107 passed, 1 skipped, 2 warnings
```

## 结论

- Phase 3 代码、真实 provider、观测和 A/B 已完成。
- 当前 Qwen3-0.6B 没有提供净准确率收益。
- 单次 classifier 平均增加约 6 秒延迟。
- 默认保持 `LLM_ROUTER_ENABLED=false`。
- 后续更换模型时可以复用同一评测和接管契约。
