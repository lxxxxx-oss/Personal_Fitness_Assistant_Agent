# 面试复习资料导航

这个目录只保留可以直接用于面试复习的事实口径。重点是理解“实现—证据—边界”的关系，不建议逐字背诵。设计原稿、阶段计划、优化台账和实现状态已经移到 `docs/technical/` 或 `docs/progress/`。

## 阅读顺序

### P0：必须掌握

先读 [01_MUST_MASTER_PROJECT_STORY.md](./01_MUST_MASTER_PROJECT_STORY.md)。

这一份是面试主线，必须能基于事实脱稿讲：

- 30 秒项目开场。
- 3 分钟项目介绍。
- 个人实际完成的工程工作。
- 能力、证据和当前边界。
- 三个主打亮点。
- 为什么使用 LangGraph 和子图。
- Router、RAG、Motion 和 Streaming 的准确口径。

### P1：最好掌握

再读 [02_SHOULD_MASTER_TECH_QA.md](./02_SHOULD_MASTER_TECH_QA.md)。

这一份用于应对技术追问：

- Python / FastAPI / SSE 基础。
- LLM、RAG、Agent 和 Tool Use 基础。
- Router eval、测试证据和泛化边界。
- async 阻塞、流式实现、Memory 和内存治理。
- 安全、权限、来源和高压追问。

### P2：了解即可

最后读 [03_GOOD_TO_KNOW_DEEP_DIVE.md](./03_GOOD_TO_KNOW_DEEP_DIVE.md)。

这一份用于深挖时兜底：

- 关键代码调用链。
- Router Phase 1 到 Phase 4 的具体实现。
- `.npz` 与图片两条 Motion 链路。
- RAG、测试证据和架构收敛决策深挖。
- 生产化顺序、白板题和演示脚本。

## 不在本目录的材料

- 原完整长版主手册：`docs/technical/interview-archive/PROJECT_INTERVIEW_GUIDE_FULL.md`
- 原子图优化总览：`docs/technical/interview-archive/SUBGRAPH_OPTIMIZATION_GUIDE.md`
- Router 技术设计和状态：`docs/technical/router/`
- Motion 技术设计和路线：`docs/technical/motion/`
- 面试准备优化计划归档：`docs/technical/interview-archive/INTERVIEW_PREPARATION_OPTIMIZATION_PLAN.md`

这些材料是证据和参考，不要求直接背诵。复习时优先看本目录的三份分级材料，并用自己的语言重新组织答案。
