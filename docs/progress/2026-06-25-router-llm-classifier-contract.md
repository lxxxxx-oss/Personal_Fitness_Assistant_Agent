# Router LLM Classifier Contract

## 目标

在不直接接入真实 LLM 的前提下，先把工程级 Router 的 Phase 3 契约固定下来：当加权规则和语义样例都无法高置信判断时，才允许尝试 LLM classifier fallback。

这一步的重点不是提高当前 eval 分数，而是明确后续接真实模型前必须满足的输入输出、解析、验收和回退边界。

## 变更内容

### 1. Router 代码

文件：

- `app/graph/router.py`

新增内容：

- `LLM_ROUTER_MIN_CONFIDENCE = 0.70`
- `ALLOWED_INTENTS`
- `_build_llm_router_prompt()`
- `_call_llm_router()`
- `_extract_json_object()`
- `_llm_classifier_route()`

当前 `_call_llm_router()` 默认返回 `None`，只作为 provider hook。也就是说当前项目还没有真实调用 LLM 做路由。

LLM classifier 只有在以下条件全部满足时才会被接受：

- 返回内容能解析出 JSON object。
- `intent` 属于 `chat/search/diet/motion/mcp`。
- `needs_clarification` 为 `false`。
- `confidence >= 0.70`。

以下情况都会回退，不会硬分流到业务子图：

- provider 未配置。
- JSON 解析失败。
- intent 非法。
- 置信度低。
- LLM 表示需要澄清。

### 2. Router 集成方式

当前顺序：

```text
weighted rules
  -> high confidence: route directly
  -> low confidence/no hit: semantic examples
  -> still uncertain: LLM classifier contract
  -> still unavailable/invalid/low confidence: fallback to chat
```

这保证了高置信、可解释的规则路径不会被 LLM 抢走。

### 3. 测试

文件：

- `tests/test_router.py`

新增测试覆盖：

- 高置信、合法 JSON 的 LLM classifier 可以接管。
- 非 JSON 返回会被拒绝。
- 低置信返回会被拒绝。
- `needs_clarification=true` 会被拒绝。

## 验证结果

Router 局部测试：

```text
python -m pytest tests/test_router.py tests/test_router_eval_script.py -q
24 passed
```

Router 评测：

```text
python scripts/eval_router.py --fail-on-mismatch
Total: 39 | Correct: 39 | Accuracy: 100.0%
fallback             3
semantic_examples    4
weighted_rules       32
```

全量测试：

```text
python -m pytest -q
76 passed, 1 skipped, 1 warning
```

## 文档同步

已同步：

- `docs/README.md`
- `docs/API.md`
- `docs/interview/PROJECT_INTERVIEW_GUIDE.md`
- `docs/interview/SUBGRAPH_OPTIMIZATION_GUIDE.md`

## 后续顺序

1. 继续扩充 router eval 中的低置信、隐式表达、多意图样本。
2. 再接真实 LLM provider，并记录 LLM 路由触发率、解析失败率、低置信率、平均延迟和成本。
3. 用 eval 对比“无 LLM fallback”和“有 LLM fallback”的收益。
4. 如果收益不足，保留当前确定性 router，把 LLM 用于生成澄清问题，而不是直接分流。
