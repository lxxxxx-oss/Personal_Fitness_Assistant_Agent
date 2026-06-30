# 2026-06-30 Router Phase 4 验收记录

## Phase 4.1 验收

测试对象：

- 多意图运行时字段。
- 主意图向后兼容。
- 次意图精确识别。
- route plan 顺序。
- 跨域模糊请求澄清标志。

命令：

```powershell
D:\Users\Lesedi\anaconda3\envs\fitness-agent\python.exe -m pytest tests\test_router.py tests\test_router_eval_script.py -q -p no:cacheprovider
D:\Users\Lesedi\anaconda3\envs\fitness-agent\python.exe scripts\eval_router.py --dataset data\eval\router_challenge_eval.jsonl
```

结果：

```text
34 passed
primary intent: 36/36, 100.0%
secondary intent exact: 36/36, 100.0%
route plan exact: 36/36, 100.0%
```

## Phase 4.2 / 4.3 验收

新增覆盖：

- 白名单组合与非白名单降级。
- 两步执行顺序和每步结果保留。
- 部分子图失败后的成功结果合成。
- 真实 LangGraph 循环拓扑下的两子图执行。
- 单路由 API、SSE 和集成路由回归。
- Search 外网失败时的空结果降级。

阶段结果：

```text
Router + API + integration: 55 passed, 1 warning
full pytest: 114 passed, 1 skipped, 1 warning
green router eval: 66/66
challenge primary/secondary/route-plan exact: 36/36
```

当前边界：

- 只支持四种两步组合，不支持任意子图排列或三步计划。
- 多意图字段仍是内部观测信息，公开 API 继续只返回主 `intent`。
- final synthesis 仍依赖本地 LLM；失败时退回各子结果的确定性拼接。
