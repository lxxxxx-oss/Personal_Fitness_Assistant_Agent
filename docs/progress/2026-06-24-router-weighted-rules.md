# Router Weighted Rule Optimization

## 背景

原 Router 使用 first-match 关键词规则：按 intent 顺序扫描，命中第一个关键词就返回对应子图。这个方案稳定、低成本，但对口语化表达和多线索输入不够友好，例如“我最近想瘦一点”容易因为“最近”被误判为 Search。

## 本次改动

### 1. 路由策略升级

修改文件：

- `app/graph/router.py`

改动内容：

- 新增 `WEIGHTED_RULES`，为不同 intent 的触发短语设置权重。
- 新增 `COMBO_RULES`，处理组合模式，例如“最近 + 瘦”偏 Diet，“最近 + 新闻”偏 Search。
- 新增 `classify_intent_with_scores()`，返回结构化 `RouteDecision`。
- 保留 `classify_intent()`，作为向后兼容入口，只返回 intent。
- `intent_classify_node()` 会将路由元信息写入 `RouterState`。

新增路由元信息：

```text
_route_scores
_route_confidence
_route_reason
_route_source
_route_matches
```

### 2. RouterState 更新

修改文件：

- `app/graph/state.py`

新增字段：

```python
_route_scores: Dict[str, float]
_route_confidence: float
_route_reason: str
_route_source: str
_route_matches: List[str]
```

### 3. 测试补充

修改文件：

- `tests/test_router.py`
- `tests/manual_level2.py`

新增覆盖：

- 口语化 Diet：`我最近想瘦一点，有什么建议？`
- Search 边界：`最近有什么健身新闻？`
- Motion 边界：`帮我看看深蹲哪里不对`
- MCP 边界：`番茄炒蛋步骤是什么？`
- Chat fallback：`蛋白质有什么作用？`
- 路由元信息：scores、confidence、reason、source、matches。

### 4. 文档同步

修改文件：

- `docs/README.md`
- `docs/API.md`
- `docs/interview/PROJECT_INTERVIEW_GUIDE.md`
- `docs/interview/SUBGRAPH_OPTIMIZATION_GUIDE.md`

同步内容：

- 将“关键词 first-match 路由”改为“加权规则路由”。
- 说明 Phase 1 已落地，Phase 2-4 为后续计划。
- 更新测试结果；Router eval 扩充后的阶段全量结果为 `72 passed, 1 skipped, 1 warning`。最新测试结果见 `2026-06-25-router-llm-classifier-contract.md`。
- 更新目录整理后的项目路径。

## 阶段验证

```text
python -m pytest -q
72 passed, 1 skipped, 1 warning
```

## 后续方向

- Phase 2：建立 `router_eval.jsonl`，实现 semantic example fallback。已在 `2026-06-24-router-semantic-examples.md` 落地轻量版本。
- Phase 3：低置信时调用 LLM classifier fallback。
- Phase 4：支持 multi-intent routing，例如 `search -> diet`。
