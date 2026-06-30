# Interview 文档导航

`docs/interview/` 用于维护面试讲解材料。这里的文档按“主入口 + 专题资料”组织，避免把所有设计、路线和台账都堆在同一层。

## 建议阅读顺序

1. [PROJECT_INTERVIEW_GUIDE.md](./PROJECT_INTERVIEW_GUIDE.md)
   - 面试主讲稿和高频问答。
   - 用于快速复习项目亮点、核心架构、实际工程难点、代码实现和边界。

2. [INTERVIEW_PREPARATION_OPTIMIZATION_PLAN.md](./INTERVIEW_PREPARATION_OPTIMIZATION_PLAN.md)
   - 面试资料审查结论、优化优先级和完成状态。
   - 后续每完成一项，需要同步更新其中的勾选状态。

3. [SUBGRAPH_OPTIMIZATION_GUIDE.md](./SUBGRAPH_OPTIMIZATION_GUIDE.md)
   - 各子图和横切能力的优化方向总览。
   - 适合回答“后续怎么优化”“为什么这么设计”。

4. [motion/MOTION_MEDIA_PIPELINE_DESIGN.md](./motion/MOTION_MEDIA_PIPELINE_DESIGN.md)
   - Motion 从 `.npz` 姿态序列扩展到图片/视频输入的需求和技术路线。

5. [motion/MOTION_OPTIMIZATION_ROADMAP.md](./motion/MOTION_OPTIMIZATION_ROADMAP.md)
   - Motion 后续优化路线和持续维护台账。
   - 每推进一步，都要记录当前状态、实际做法和路线偏差。

6. [router/MULTI_INTENT_ROUTING_DESIGN.md](./router/MULTI_INTENT_ROUTING_DESIGN.md)
   - Router 多意图识别和多子图编排的后续设计。
   - Phase 4.1～4.3 已落地；当前只执行四种白名单两步组合，不开放任意子图串联。

7. [router/ROUTER_OPTIMIZATION_STATUS.md](./router/ROUTER_OPTIMIZATION_STATUS.md)
   - Router 当前优化进度、评测基线和下一步优先级。
   - 用于快速判断“现在做到哪一步了”。

## 目录职责

```text
docs/interview/
  README.md                         # 本导航
  PROJECT_INTERVIEW_GUIDE.md         # 面试主文档
  INTERVIEW_PREPARATION_OPTIMIZATION_PLAN.md # 面试准备优化状态
  SUBGRAPH_OPTIMIZATION_GUIDE.md     # 子图优化总览
  motion/                            # Motion 专题
  router/                            # Router 专题
```

## 维护规则

- 面试主线、项目亮点、通用 Q&A：优先更新 `PROJECT_INTERVIEW_GUIDE.md`。
- 面试准备优先级和完成状态：更新 `INTERVIEW_PREPARATION_OPTIMIZATION_PLAN.md`。
- 子图优化方向总览：优先更新 `SUBGRAPH_OPTIMIZATION_GUIDE.md`。
- Motion 图片/视频路线、姿态估计、标准动作库、评测：优先更新 `motion/`。
- Router 当前进度、多意图、挑战集、路由演进：优先更新 `router/`。
- 不要把规划项写成已实现能力；必须区分“当前已实现”“当前边界”“后续路线”。
