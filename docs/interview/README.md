# 面试复习资料导航

这个目录只保留可以直接用于面试复习的事实口径。重点不是逐字背诵，而是学会用“项目思路、技术取舍、问题解决、能力边界”来回答面试官。

面试回答不要像百科定义。大多数问题都可以按下面顺序组织：

```text
面试官真正想了解什么
  -> 我当时为什么这样设计
  -> 我比较过哪些方案或遇到过什么问题
  -> 当前做到哪里，有什么证据
  -> 当前边界是什么，为什么先设置这个边界
  -> 如果生产化，下一步怎么做
```

设计原稿、阶段计划、优化台账和实现状态已经移到 `docs/technical/` 或 `docs/progress/`。

## 简历口径优先

`docs/interview/agent.json` 是本地简历源文件，包含个人信息，不上传到 GitHub。面试复习材料要围绕简历中的项目描述来组织：简历里写到的技术点，就是面试官最可能追问的技术点。

如果简历表述比当前代码更“前置”，本目录的任务不是简单否定简历，而是准备可防守回答：

- 这个技术点为什么写进简历。
- 当前项目哪部分已经支撑它。
- 哪些部分还属于目标架构或后续生产化。
- 面试官追问代码时，如何解释当前边界和补齐路径。

也就是说，简历是对外主线，interview 文档负责把这条主线讲清楚、讲稳、讲得能应对追问。

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

这一份用于应对技术追问，但重点不是背定义，而是讲清楚“我为什么这么选、怎么发现问题、为什么设置边界”：

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
