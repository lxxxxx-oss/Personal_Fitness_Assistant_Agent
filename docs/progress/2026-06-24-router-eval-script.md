# Router Eval Script

## 背景

Router 已完成 weighted rule scoring 和 semantic examples fallback。继续优化前需要先有稳定评测脚本，避免后续调规则、加样例或接 LLM classifier 时只凭感觉判断效果。

## 本次改动

### 1. 新增评测脚本

新增文件：

- `scripts/eval_router.py`

默认读取：

```text
data/eval/router_eval.jsonl
```

输出内容：

- overall accuracy。
- per-intent precision / recall / F1。
- support 和 predicted count。
- confusion matrix。
- route source counts，例如 `weighted_rules`、`semantic_examples`、`fallback`。
- mismatch 明细，包括 expected、predicted、confidence、source、reason。

使用方式：

```bash
python scripts/eval_router.py --fail-on-mismatch
python scripts/eval_router.py --json
python scripts/eval_router.py --show-cases
```

### 2. 新增测试

新增文件：

- `tests/test_router_eval_script.py`

覆盖：

- `data/eval/router_eval.jsonl` 可以正常加载。
- 当前 Router 在评测集上 accuracy 为 1.0。
- 输出包含五类 intent 的指标。

## 当前结果

```text
python scripts/eval_router.py --fail-on-mismatch

Total: 19 | Correct: 19 | Accuracy: 100.0%

Route source counts:
fallback             1
semantic_examples    3
weighted_rules       15
```

## 后续方向

- 扩充 `router_eval.jsonl`，加入更多边界样本和多意图样本。
- 在脚本中增加宏平均 / 加权平均 F1。
- 增加输出文件参数，便于 CI 保存评测报告。
- 接入 LLM classifier fallback 后，用同一脚本比较前后效果。
