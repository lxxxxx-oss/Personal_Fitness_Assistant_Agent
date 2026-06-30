# 面试背诵资料导航

这个目录只保留可以直接用于面试复习和背诵的内容。设计原稿、阶段计划、优化台账和实现状态已经移到 `docs/technical/` 或 `docs/progress/`，避免复习时被过程材料打断。

## 阅读顺序

### P0：必须掌握

先读 [01_MUST_MASTER_PROJECT_STORY.md](./01_MUST_MASTER_PROJECT_STORY.md)。

这一份是面试主线，必须能脱稿讲：

- 30 秒项目开场。
- 3 分钟项目介绍。
- 三个主打亮点。
- 为什么不是 ChatGPT 套壳。
- 为什么使用 LangGraph 和子图。
- Router、RAG、Motion、MCP、Streaming、Memory 的核心口径。
- 当前已实现、当前边界、后续怎么升级。

### P1：最好掌握

再读 [02_SHOULD_MASTER_TECH_QA.md](./02_SHOULD_MASTER_TECH_QA.md)。

这一份用于应对技术追问：

- Python / FastAPI / SSE 基础。
- LLM、RAG、Agent、Tool Use、MCP 基础。
- Router eval、失败降级、内存治理。
- 项目和基础知识如何连接。

### P2：了解即可

最后读 [03_GOOD_TO_KNOW_DEEP_DIVE.md](./03_GOOD_TO_KNOW_DEEP_DIVE.md)。

这一份用于深挖时兜底：

- 关键代码调用链。
- Router Phase 1 到 Phase 4。
- Motion 图片/视频路线。
- 生产化升级路径。
- 白板题和反问模板。

## 不在本目录的材料

- 原完整长版主手册：`docs/technical/interview-archive/PROJECT_INTERVIEW_GUIDE_FULL.md`
- 原子图优化总览：`docs/technical/interview-archive/SUBGRAPH_OPTIMIZATION_GUIDE.md`
- Router 技术设计和状态：`docs/technical/router/`
- Motion 技术设计和路线：`docs/technical/motion/`
- 面试准备优化计划：`docs/progress/INTERVIEW_PREPARATION_OPTIMIZATION_PLAN.md`

这些材料是证据和参考，不要求直接背诵。复习时优先看本目录的三份分级材料。
