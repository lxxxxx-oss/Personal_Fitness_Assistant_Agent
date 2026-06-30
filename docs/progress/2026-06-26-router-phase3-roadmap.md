# Router Phase 3 Roadmap整理

## 背景

现有 Router 优化路线已经形成清晰分层：

- Phase 1：Weighted Rule Router
- Phase 2：Semantic Example Router
- Phase 3：LLM Classifier Fallback
- Phase 4：Multi-intent Routing

但此前 Phase 3 在文档里更偏“代码契约说明”，缺少一份适合面试讲述和后续落地排期的完整口径，容易和 Phase 4 的 multi-intent 设计混在一起。

## 本次整理内容

本次没有改动 Router 代码，只对文档做了梳理和收口：

- 重写 `docs/interview/SUBGRAPH_OPTIMIZATION_GUIDE.md` 中的 Phase 3 章节。
- 明确 Phase 3 的目标是“单 intent 下的低置信歧义裁决”，不是把 Router 全量交给 LLM。
- 明确 Phase 3 的工程边界：只做 JSON intent classifier，不生成回答，不替换高置信规则，不提前进入多子图串联。
- 补充建议实施顺序：先补 challenge/eval，再接 provider，再看收益数据。
- 补充验收口径：看 challenge set 改善、触发率、解析失败率、延迟和成本，而不是只看“更智能”。
- 补充与 Phase 4 的关系说明，避免把“歧义分类”和“multi-intent route plan”混为一谈。

## 同步文档

- `docs/interview/SUBGRAPH_OPTIMIZATION_GUIDE.md`
- `docs/README.md`

## 统一后的讲法

更适合面试时统一表达为：

> Phase 1 和 Phase 2 先把高置信规则路由和轻量语义兜底做好，Phase 3 才考虑引入低频 LLM fallback，专门处理 challenge set 里那些规则和样例都拿不准的歧义句式。它不是主路由，更不是直接替代 Router，而是一个带严格 JSON 契约、低置信回退和观测指标的受控分类器。

## Next Steps

1. 继续补充 Router challenge set，重点覆盖歧义句式、顺序词、否定约束和多信号竞争样本。
2. 在不改变现有主路由行为的前提下，增加 Phase 3 触发统计与观测字段。
3. 用 mock 或真实 provider 做 A/B 对比，再决定是否保留真实 LLM fallback。
