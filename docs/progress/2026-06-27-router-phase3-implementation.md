# 2026-06-27 Router Phase 3 实施记录

## 操作类型

Router 优化、评测增强、LLM classifier 接入。

## 实施原则

按以下顺序推进，每个阶段单独验证并记录：

1. 确定性边界修正。
2. Ambiguity detector 与触发观测。
3. 本地 Qwen provider 接入。
4. 关闭/开启 LLM 的 A/B 评测。

验收底线：绿色回归集保持 `66/66`；真实 LLM 没有稳定收益时默认关闭。

## Checkpoint 1：确定性边界修正

状态：已完成。

本阶段没有调用 LLM，只处理 challenge set 已暴露且可以明确编码的业务约束：

- `先...再...`：提升第一个明确任务的 primary intent。
- `不需要具体做法`、`不想做饭`：抑制 `mcp`，提升饮食规划。
- `找一找`、`权威说法`、`有没有...研究`：强化显式检索。
- `吃和练`、`体重没变`：综合问题优先 `chat`。
- `练什么动作`：没有姿态分析信号时按训练计划进入 `chat`。
- `用冰箱里的...安排一顿`：按具体食材构造进入 `mcp`。

评测结果：

```text
绿色回归集：66/66，100.0%
原 Challenge Set：20/20，100.0%
扩充后 Challenge Set：36/36，100.0%
```

阶段判断：

- 已修复现有 9 条 mismatch。
- 绿色回归行为没有退化。
- 已将 challenge set 从 20 条扩充到 36 条，增加顺序词、否定表达、权威检索、计划边界和食材构造变体。
- 扩充后的首次评测为 32/36；继续补充通用模式后达到 36/36。
- 当前结果仍是离线小样本基线，不能等同于生产泛化能力。

## Checkpoint 2：Ambiguity Detector 与观测

状态：已完成。

新增能力：

- RouteDecision 和 RouterState 记录 `_route_ambiguity_signals`。
- 检测顺序任务、否定约束、跨域计划、进展诊断、plan-vs-motion、diet-vs-recipe、权威检索和规则分数接近。
- 评测脚本输出 ambiguity signal counts。
- 记录 LLM 调用 outcome、平均延迟和最大延迟。

触发策略经过一次收缩：

- 第一版困难集有 27/36 会尝试 LLM，频率过高。
- 调整后只让 `close_rule_scores`、`cross_domain_plan`、`progress_diagnosis` 触发 LLM review。
- 顺序词、否定约束、权威检索等已有确定性结论的信号只记录，不调用模型。
- 当前 challenge set LLM review 触发率为 5/36。

测试：

```text
tests/test_router.py + tests/test_router_eval_script.py
30 passed
```

## Checkpoint 3：本地 Qwen Provider

状态：已完成，默认关闭。

实现内容：

- 新增 `LLM_ROUTER_ENABLED`，默认 `false`。
- 新增 `LLM_ROUTER_MAX_TOKENS`，默认 128。
- `_call_llm_router()` 接入项目共享 `LLMLoader`，不会重复加载模型。
- 使用 `temperature=0`、严格 JSON 和 `/no_think` 提示。
- 模型输出非法 JSON、非法 intent、低置信或需要澄清时拒绝接管。
- 高置信规则场景中，LLM 置信度必须高于规则置信度。

Prompt 调整过程：

1. 英文 zero-shot：模型误判输入为空，低置信拒绝。
2. 中文 few-shot：模型复制第一个 search 示例，产生错误高置信。
3. 简洁中文 zero-shot：分类可用，但 reason 仍有轻微幻觉。

结论：0.6B 模型可以完成工程接入，但模型自述 reason 不可靠，必须依赖外部评测和接管保护。

## Checkpoint 4：A/B 评测

状态：已完成。

关闭真实 LLM：

```text
green: 66/66
challenge: 36/36
```

第一次开启真实 LLM但尚未增加规则置信度保护：

```text
challenge: 35/36
错误：减脂晚餐具体怎么做，mcp -> diet
```

增加“LLM 置信度必须高于规则置信度”后：

```text
green: 66/66
challenge: 36/36
challenge LLM calls: 5
challenge selected: 1
challenge rejected_not_higher_confidence: 4
challenge average latency: 6221.92 ms
```

最终决策：

- Phase 3 工程实现完成。
- 本地 Qwen 没有带来净准确率收益，并引入明显延迟。
- `LLM_ROUTER_ENABLED` 默认保持关闭。
- 保留 provider、严格契约、ambiguity signals 和 metrics，供后续换更强模型时复用。
- 下一步进入 Phase 4.1，只记录 multi-intent 字段，不执行多子图串联。

## 工具接口规范检查

结论：通过。

- 职责清晰：LLM provider 只做 intent classification，不生成业务回答。
- 输入清晰：输入是完整分类 prompt，输出要求固定 JSON schema。
- 输出清晰：使用 `RouteDecision`，包含 intent、confidence、reason、source、scores、matches 和 ambiguity signals。
- 权限清晰：只调用本地模型，不访问网络或写外部数据。
- 错误可处理：disabled、parse error、invalid intent、low confidence、clarification 都有独立 outcome 并安全回退。
