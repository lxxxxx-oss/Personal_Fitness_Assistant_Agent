# 2026-06-30 面试官视角审查与材料收紧

## 操作类型

面试文档审查 / 事实边界修正 / 技术追问补强。

## 背景

从严格 AI Agent 面试官角度审查 `docs/interview/` 后，发现原材料主线清楚，但 Motion、测试基线、流式输出和 Router 指标存在被过度理解的风险；个人贡献、真实代码边界、安全和高压追问也不够集中。

## 本次调整

- 重写 P0，增加个人工程工作和“能力—证据—边界”矩阵。
- 明确 Router 102 条样本属于自建回归证据，不代表线上泛化。
- 明确 114 条 pytest 大量使用 mock，只证明确定性逻辑和契约回归。
- 区分 Motion `.npz` 分析链路与图片静态姿态提取链路。
- 明确 SSE 的同步阻塞边界，以及 WebSocket 当前先缓存 token 后发送。
- 将多意图能力表述为受控两步编排，而不是通用 Planner。
- 补充 RAG 来源暴露、MCP 核心子集、Memory、安全和可观测性边界。
- 在 P1 增加面试官高压追问，在 P2 增加真实调用链、白板图和演示顺序。
- 弱化逐字背诵和反复使用“不是套壳”的表达。

## 影响范围

- `docs/interview/README.md`
- `docs/interview/01_MUST_MASTER_PROJECT_STORY.md`
- `docs/interview/02_SHOULD_MASTER_TECH_QA.md`
- `docs/interview/03_GOOD_TO_KNOW_DEEP_DIVE.md`
- `docs/README.md`
- `docs/DOCUMENTATION_MAP.md`
- `docs/technical/interview-archive/PROJECT_INTERVIEW_GUIDE_FULL.md`
- `docs/technical/interview-archive/SUBGRAPH_OPTIMIZATION_GUIDE.md`

没有修改代码、配置、接口或测试源码。

## 验证

- 面试材料中的关键实现表述已与当前 Router、FastAPI、Motion、MCP 和测试代码逐项对照。
- 已检查本地 Markdown 链接和 progress 最近 10 条规则。

## 下一步

结合真实模拟面试记录，继续删减答题模板，补充面试官实际追问和用户自己的口语化回答。
