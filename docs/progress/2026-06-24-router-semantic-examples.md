# Router Semantic Example Fallback

## 背景

Phase 1 已将 Router 从 first-match 关键词升级为 weighted rule scoring。继续优化的目标是处理规则低置信或没有明确关键词的隐式表达，例如：

```text
我想把身材调整得更轻盈一点
晚饭做什么菜？
什么是渐进超负荷？
```

这些问题不一定包含高权重触发词，但语义上仍然应进入 Diet、MCP 或 Chat。

## 本次改动

### 1. 新增 Semantic Examples

修改文件：

- `app/graph/router.py`

新增：

- `SEMANTIC_EXAMPLES`
- `_semantic_features()`
- `_semantic_route()`

当前实现使用 char n-gram Jaccard 相似度，不新增模型下载或外部服务依赖。规则高置信时仍直接走 weighted rules；规则低置信或没有命中时，才尝试 semantic examples fallback。

命中 semantic fallback 时：

```text
_route_source = "semantic_examples"
```

### 2. Chat 参与概念类打分

为 `chat` 增加概念解释类规则：

```text
什么是
是什么
有什么作用
有哪些好处
原理
概念
```

这样 `深蹲有哪些好处？`、`蛋白质有什么作用？` 这类知识解释问题可以进入 Chat，而不是因为命中动作名或营养词被误分到 Motion / Diet。

### 3. 新增 Router 评测集

新增文件：

- `data/eval/router_eval.jsonl`

内容覆盖：

- 口语化 Diet。
- 隐式 Search。
- Motion 姿态分析。
- MCP 菜谱/做菜。
- Chat 概念解释和 fallback。

### 4. 测试更新

修改文件：

- `tests/test_router.py`
- `tests/manual_level2.py`

新增测试：

- semantic examples 能处理隐式 Diet。
- semantic examples 能处理隐式 MCP。
- Chat 能赢过概念解释类问题。
- 测试读取 `data/eval/router_eval.jsonl` 并验证当前 Router 输出。

## 当前验证

```text
python -m pytest tests/test_router.py -q
17 passed

python -m pytest -q
72 passed, 1 skipped, 1 warning
```

备注：这是本阶段当时的验证结果；最新全量结果见 `2026-06-25-router-llm-classifier-contract.md`。

## 后续方向

- 将 char n-gram 相似度替换为 Sentence-Transformer embedding 相似度。
- 缓存 semantic examples 的 embedding。
- 增加 router eval 统计脚本，输出 accuracy、per-intent precision/recall、confusion matrix。
- 在低置信样本上接入 LLM classifier fallback。
