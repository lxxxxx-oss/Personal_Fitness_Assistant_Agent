# Router Eval Mainstream Slices

## 目标

继续扩充 `data/eval/router_eval.jsonl`，但不做随意堆样本，而是按主流 intent routing 评测方式组织样本，方便面试时解释：

- 为什么要测这些样本。
- 每类样本对应什么真实失败模式。
- 单 intent Router 遇到多意图时如何定义 primary intent。

## 主流评测切片

本次新增样本使用以下切片：

- `implicit_intent`：用户不直接说“饮食/动作分析/搜索”，但语义上属于某个子图。
- `low_confidence`：表达很泛，适合验证低置信语义 fallback。
- `fallback_unclear`：不清楚或开放式表达，应该安全回到 `chat`。
- `freshness_search`：包含最新、今年、研究、查找等时效性检索意图。
- `multi_intent_primary`：一句话里有多个意图，用 primary intent policy 标注。
- `boundary_concept`：概念解释不应误进 Diet 或 Motion。
- `boundary_training_plan`：泛化训练计划留在 Chat RAG，而不是误进 Motion 或 MCP。
- `recipe_tool`：具体做菜、食材、晚餐请求进入 MCP。
- `tool_file_signal`：`.npz`、pose 文件、上传动作数据进入 Motion。

## Primary Intent Policy

当前 Router 仍是单 intent 分流，因此多意图样本要先定义主意图：

```text
显式搜索 / 最新研究 / 查找资料 -> search
动作文件 / 姿势判断 / 技术问题 -> motion
具体菜谱 / 食材做法 / 晚餐菜 -> mcp
个人饮食规划 / 摄入量 / 减脂增肌饮食 -> diet
泛化训练建议 / 概念解释 / 不明确表达 -> chat
```

这个策略适合面试解释：在没有 multi-intent route plan 之前，先保证单 intent Router 的行为一致、可解释、可评测。

## 代码变更

### 1. 评测数据

文件：

- `data/eval/router_eval.jsonl`

变更：

- 从 39 条扩充到 66 条。
- 新增样本带 `category` 字段，用于评测切片统计。

### 2. 评测脚本

文件：

- `scripts/eval_router.py`

变更：

- 增加 `by_category` 统计。
- 文本报告新增 `Evaluation slices` 区块。
- JSON 输出也包含 `by_category`。

### 3. Router 规则小补强

文件：

- `app/graph/router.py`

补强方向：

- 显式搜索触发词：`搜一下`、`找一下`。
- 具体做菜触发词：`晚餐`、`低脂晚餐`、`高蛋白晚餐`、`鸡胸肉`、`沙拉`。
- 泛化训练计划和不明确表达：`训练计划`、`训练建议`、`怎么练`、`练点什么`、`不需要器械`、`不知道该问`、`先给我个建议`。

这些规则服务于 primary intent policy，不引入新模型依赖。

### 4. 测试

文件：

- `tests/test_router_eval_script.py`

变更：

- 增加 `by_category` 存在性断言。

## 验证结果

Router Eval：

```text
python scripts/eval_router.py --fail-on-mismatch
Total: 66 | Correct: 66 | Accuracy: 100.0%
```

Evaluation slices：

```text
boundary_concept               2/2
boundary_training_plan         3/3
fallback_unclear               3/3
freshness_search               3/3
implicit_intent                6/6
low_confidence                 1/1
multi_intent_primary           4/4
recipe_tool                    3/3
tool_file_signal               2/2
uncategorized                 39/39
```

Route source counts：

```text
fallback             4
semantic_examples    6
weighted_rules       56
```

全量测试：

```text
python -m pytest -q
76 passed, 1 skipped, 1 warning
```

## 面试说法

可以这样讲：

> Router eval 不是只堆一些容易命中的关键词样本，而是按 intent routing 常见失败模式做切片评测：隐式意图、低置信兜底、多意图 primary routing、概念解释边界、训练计划边界、具体工具触发和文件信号。这样调规则时可以看到是哪个切片变好了或变差了，而不是只看总 accuracy。

需要注意：

- 当前 66 条仍然是项目级小评测集，不是大规模生产数据集。
- 100% accuracy 只代表当前标注样本全部通过，不能说泛化准确率已经 100%。
- 后续接真实 LLM classifier 前，应继续扩充 `low_confidence` 和 `multi_intent_primary` 样本，并加入失败样本回归集。
