# 2026-06-25 Interview 文档目录整理

## 操作类型

文档结构整理。

## 背景

`docs/interview/` 中同时放置了面试主指南、子图优化总览、Router 专题设计、Motion 媒体路线和 Motion Roadmap，根目录文件逐渐变多，阅读入口不够清晰。

## 本次变更

新增导航：

- `docs/interview/README.md`

保留在 `docs/interview/` 根目录：

- `PROJECT_INTERVIEW_GUIDE.md`
- `SUBGRAPH_OPTIMIZATION_GUIDE.md`

移动到专题目录：

- `docs/interview/motion/MOTION_MEDIA_PIPELINE_DESIGN.md`
- `docs/interview/motion/MOTION_OPTIMIZATION_ROADMAP.md`
- `docs/interview/router/MULTI_INTENT_ROUTING_DESIGN.md`

同步更新引用：

- `docs/README.md`
- `docs/interview/PROJECT_INTERVIEW_GUIDE.md`
- `docs/interview/SUBGRAPH_OPTIMIZATION_GUIDE.md`
- `docs/interview/motion/MOTION_OPTIMIZATION_ROADMAP.md`
- 相关 progress 记录中的当前路径引用

## 影响范围

- 仅调整文档目录和链接。
- 未修改代码。
- 未修改 API。
- 未修改测试。

## 后续维护规则

- 面试主线和 Q&A：维护 `PROJECT_INTERVIEW_GUIDE.md`。
- 子图优化总览：维护 `SUBGRAPH_OPTIMIZATION_GUIDE.md`。
- Motion 媒体路线、姿态估计、Roadmap：维护 `docs/interview/motion/`。
- Router 多意图设计：维护 `docs/interview/router/`。

## 验证

本次为文档结构调整，未运行自动化测试。

已通过 `rg` 检查旧路径引用，确保主要入口文档已指向新目录。
