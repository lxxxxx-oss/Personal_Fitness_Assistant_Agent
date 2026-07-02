# Tests 验收记录索引

`docs/tests/` 用于保存手工测试、冒烟测试、专项验证和遗留风险。这里记录的是“测过什么、结果是什么、还剩什么风险”，不是自动化测试源码。

## 快速结论

当前文档化验收覆盖了这些方向：

- 基础端点冒烟和核心链路。
- Router 绿色回归集与 challenge set。
- Motion `PoseSequence`、姿态估计适配器，以及真实图片/视频姿态链路。
- MCP 默认 mock 和真实 server fallback。
- Web UI 对话等待状态和 Motion 图片上传入口。
- 面试/演示用手工体验语句。

自动化测试的当前总结果以 [../README.md](../README.md) 中“当前测试结果”为准；本目录用于记录测试过程和验收依据。

## 验收矩阵

| 能力 | 验收记录 | 结论口径 |
|---|---|---|
| 小程序回答元数据 | [2026-07-02-miniprogram-result-contract.md](./2026-07-02-miniprogram-result-contract.md) | sources/warnings 在 HTTP、SSE、WebSocket 与小程序消息卡片间完成闭环 |
| 全端点冒烟 | [2026-06-10-level-1-smoke-test.md](./2026-06-10-level-1-smoke-test.md) | 早期全端点冒烟，记录 Motion 和 SSE 初期问题 |
| 核心链路 | [2026-06-10-level-2-core-link.md](./2026-06-10-level-2-core-link.md) | 路由、SSE、WebSocket 核心链路验证 |
| 手工体验语句 | [2026-06-23-manual-test-prompts.md](./2026-06-23-manual-test-prompts.md) | 面试/演示前可用的接口、对话、Motion 上传和异常测试语句 |
| Router eval | [2026-06-25-router-eval-and-challenge-test.md](./2026-06-25-router-eval-and-challenge-test.md) | 绿色回归集 66/66，challenge set 用于记录困难边界 |
| Motion `PoseSequence` | [2026-06-25-motion-pose-sequence-schema.md](./2026-06-25-motion-pose-sequence-schema.md) | 中间格式、metadata、legacy `.npz` 兼容验证 |
| Motion 姿态估计适配器 | [2026-06-25-motion-pose-estimator-adapter.md](./2026-06-25-motion-pose-estimator-adapter.md) | 图片数组校验、MediaPipe 缺失降级、landmark 转换验证 |
| Motion 图片静态分析 | [2026-06-26-motion-image-static-analysis.md](./2026-06-26-motion-image-static-analysis.md) | `/motion/analyze-image` 的接口和降级行为验证 |
| MCP fallback | [2026-06-26-mcp-default-mock-fallback.md](./2026-06-26-mcp-default-mock-fallback.md) | 默认 mock、真实 server 失败降级和集成测试记录 |
| Web UI 等待状态 | [2026-06-26-web-ui-chat-pending-state.md](./2026-06-26-web-ui-chat-pending-state.md) | 提问后 pending 状态、intent meta 状态更新、错误展示验证 |
| Web UI 图片上传 | [2026-06-26-web-ui-motion-image-upload.md](./2026-06-26-web-ui-motion-image-upload.md) | 图片上传入口、手工上传反馈和遗留风险记录 |
| Motion 真实图片 | [2026-07-02-motion-real-image-smoke.md](./2026-07-02-motion-real-image-smoke.md) | 官方模型真实推理与 `/motion/analyze-image` HTTP 200 |
| Motion 真实视频 | [2026-07-02-motion-real-video-smoke.md](./2026-07-02-motion-real-video-smoke.md) | OpenCV 抽帧、MediaPipe VIDEO 与多帧 PoseSequence HTTP 200 |
| LLM 内存安全 | [2026-06-27-llm-memory-oom-fix.md](./2026-06-27-llm-memory-oom-fix.md) | 共享模型缓存、并发首次加载、流式单次生成回归验证 |
| Router Phase 3 A/B | [2026-06-27-router-phase3-ab-eval.md](./2026-06-27-router-phase3-ab-eval.md) | 36 条 challenge、真实 Qwen 接入、延迟和接管收益评测 |
| Router Phase 4 | [2026-06-30-router-phase4-eval.md](./2026-06-30-router-phase4-eval.md) | 多意图字段、受控组合执行、结果合成与降级验证 |

## 面试时怎么用

如果被问“你怎么证明项目不是只写了功能”，可以按这个顺序回答：

1. Router 有绿色回归集和 challenge set，不只看总 accuracy，还记录 evaluation slices、route source counts 和困难边界。
2. Motion 的媒体输入不是口头规划，`PoseSequence`、真实图片和最小视频链路都有专项验收记录。
3. MCP 和 Web UI 都记录了降级和用户体验相关验收，说明项目关注演示稳定性和失败路径。
4. 早期 Level 1/2 测试记录保留了核心链路从问题到修复的过程。

## 维护规则

- 新增自动化测试或手工验收后，优先追加日期记录。
- 记录里要写清楚测试对象、命令或操作、结果、遗留风险。
- 新增测试记录后，同步更新本索引的验收矩阵。
- 当前真实能力边界仍以 `docs/README.md` 和相关专题文档为准。
- 如果测试结果改变了当前可展示状态或总测试结论，还要同步 `docs/README.md`。
