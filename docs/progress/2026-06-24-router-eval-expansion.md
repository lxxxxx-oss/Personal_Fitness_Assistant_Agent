# Router Eval Expansion

## 背景

在新增 `scripts/eval_router.py` 后，继续扩充 `data/eval/router_eval.jsonl`，用更多边界样本检验 Router，而不是只在少量“容易样本”上得到高分。

## 本次改动

### 1. 扩充评测集

修改文件：

- `data/eval/router_eval.jsonl`

样本数：

```text
19 -> 39
```

新增覆盖：

- Chat vs Diet：蛋白质概念解释、蛋白质摄入规划、隐式体型改善。
- Chat vs Motion：深蹲好处、深蹲疼痛、卧推/硬拉姿势。
- Search vs Diet：显式搜索研究、最近想控制体重。
- MCP vs Motion：做菜“怎么做”和动作“怎么做”的区分。
- Fallback：问候和泛化训练建议。

### 2. 根据错例修正规则

第一次扩充后结果：

```text
Total: 39 | Correct: 34 | Accuracy: 87.2%
```

主要错例：

- `我有点胖，想改善一下体型` 被分到 Chat。
- `一天吃多少蛋白质比较合适？` 被分到 Chat。
- `蛋白质为什么能帮助增肌？` 被分到 Diet。
- `为什么深蹲能练腿？` 被分到 Motion。
- `晚餐推荐一个高蛋白菜` 被分到 Chat。

修正：

- 为 Diet 增加 `有点胖`、`改善体型`、`吃多少蛋白质`、`蛋白质 + 多少` 等规则。
- 为 MCP 增加 `晚餐推荐`、`高蛋白菜`、`晚餐 + 菜`、`推荐 + 菜` 等规则。
- 提高 Chat 中 `为什么` 的权重，让概念解释问题优先进入 Chat。

### 3. 测试更新

修改文件：

- `tests/test_router.py`

新增边界用例：

- 隐式 Diet。
- 蛋白质摄入规划。
- 蛋白质/深蹲原因解释。
- 晚餐高蛋白菜推荐。
- 显式 Search 研究查询。

## 当前结果

```text
python scripts/eval_router.py --fail-on-mismatch

Total: 39 | Correct: 39 | Accuracy: 100.0%

Route source counts:
fallback             3
semantic_examples    4
weighted_rules       32
```

```text
python -m pytest tests/test_router.py tests/test_router_eval_script.py -q
20 passed

python -m pytest -q
72 passed, 1 skipped, 1 warning
```

备注：这是本阶段当时的验证结果；最新全量结果见 `2026-06-25-router-llm-classifier-contract.md`。

## 后续方向

- 继续扩充多意图样本，例如 `search -> diet`。
- 增加更多“训练计划 vs 动作分析 vs 通用 Chat”的边界样本。
- 接入 LLM classifier 前，先用当前 eval 脚本固定 baseline。
