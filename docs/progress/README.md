# Progress 最近记录

`docs/progress/` 保存日期化实现、修复和文档调整记录。本页只索引最近 10 条，避免导航继续膨胀；未列出的旧文件作为历史证据保留。当前项目状态仍以 [../README.md](../README.md) 为准，测试证据看 [../tests/README.md](../tests/README.md)。

保留规则：

- 索引按日期倒序展示最近 10 条；同一天按文件名倒序确定顺序。
- 新增记录时从索引移除最旧条目，但不要求删除历史文件。
- 长期有效的设计结论沉淀到 `technical/`，接口和运行事实沉淀到 `API.md`、`README.md` 或 `RUNBOOK.md`。
- progress 是近期过程记录，不承担长期档案库职责。

## 最近 10 条

| 日期 | 记录 | 重点 |
|---|---|---|
| 2026-07-08 | [本地原型安全与部署边界](./2026-07-08-local-prototype-security-boundary.md) | 明确无鉴权、CORS、内存会话和 liveness/readiness 边界 |
| 2026-07-08 | [GitHub 首屏与架构入口](./2026-07-08-root-readme-and-architecture.md) | 新增根 README，用 Mermaid 区分对话 Agent 与独立媒体 API |
| 2026-07-08 | [测试与真实依赖边界审计](./2026-07-08-test-and-dependency-boundary-audit.md) | 区分 mock 自动化、真实依赖验收和 MCP 协议原型边界 |
| 2026-07-08 | [API 输入边界加固](./2026-07-08-api-input-boundary-hardening.md) | 后端强制图片 10MB 上限，WebSocket 复用 HTTP 字段契约 |
| 2026-07-08 | [文档与运行时边界审计](./2026-07-08-documentation-runtime-boundary-audit.md) | 修正跨任务记忆、媒体 Motion、关节角和 ReAct 的事实口径 |
| 2026-07-07 | [黄金演示闭环阶段 4：WebSocket 真流式与真实媒体冒烟](./2026-07-07-websocket-true-streaming-and-golden-smoke.md) | 修复 token 全量缓冲，回归首 token 实时到达，并复验真实图片/视频 MediaPipe 链路 |
| 2026-07-07 | [Motion 视频 PoseSequence 相似度闭环](./2026-07-07-video-pose-similarity-closure.md) | 同 schema 标准视频构建、髋中心归一化、FastDTW 多指标比较和小程序参考选择 |
| 2026-07-07 | [黄金演示闭环阶段 3：小程序 Motion 视频上传](./2026-07-07-miniprogram-motion-video-upload.md) | 视频选择、30MB 校验、上传进度、本地播放、多帧姿态摘要和真实执行标签闭环 |
| 2026-07-07 | [黄金演示闭环阶段 2：小程序 Motion 图片上传](./2026-07-07-miniprogram-motion-image-upload.md) | 小程序完成图片选择、预览、上传、MediaPipe 静态姿态摘要和真实执行标签闭环 |
| 2026-07-07 | [黄金演示闭环阶段 1：执行模式可见性](./2026-07-07-execution-mode-visibility.md) | 对话公开真实/mock/fallback 执行轨迹，小程序展示模式标签，并修复环境变量解析 |
| 2026-07-02 | [小程序阶段 1：回答元数据闭环](./2026-07-02-miniprogram-result-contract.md) | 三种对话协议统一透传 sources/warnings，小程序增加来源与运行提示卡片 |
| 2026-07-01/02 | [Milvus RAG 接入与验证记录](./2026-07-01-milvus-rag-wip.md) | Retriever、索引、内存降级和 Compose 已加入；SDK 与容器健康已确认，真实 CRUD 冒烟仍待完成 |
| 2026-06-30 | [Interview 简历口径修正](./2026-06-30-interview-resume-alignment-fix.md) | 移除默认看代码假设，按简历主线重写 P0/P1/P2 面试材料 |
| 2026-06-30 | [简历口径优先规则](./2026-06-30-resume-first-interview-rule.md) | 忽略本地简历 JSON，interview 材料围绕简历项目描述组织 |
| 2026-06-30 | [面试回答风格再梳理](./2026-06-30-interview-answer-style-refinement.md) | 从标准答案改为项目思路、技术取舍、问题解决和边界说明 |

## 维护方式

新增记录必须写清：变更概述、影响范围、验证结果、遗留问题和下一步。记录完成后，同时检查：

- 是否需要更新 `docs/README.md` 的当前状态。
- 是否改变 `docs/API.md` 的接口事实。
- 是否改变 `docs/RUNBOOK.md` 的运行方式。
- 是否需要在 `docs/tests/` 增加验收记录。
