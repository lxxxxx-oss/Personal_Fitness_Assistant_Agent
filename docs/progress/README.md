# Progress 记录索引

`docs/progress/` 用于保留阶段性实现、重构、修复和文档整理记录。这里的单篇日期文档是证据，不建议删除；日常阅读优先看本索引，需要追溯细节时再打开对应记录。

## 阅读方式

- 想了解项目当前状态：先看 [../README.md](../README.md)。
- 想了解文档整体脉络：看 [../DOCUMENTATION_MAP.md](../DOCUMENTATION_MAP.md)。
- 想追溯某个能力怎么演进：在本页按主题找对应记录。
- 想证明某项能力验证过：看 [../tests/README.md](../tests/README.md)。

## 主题索引

### 1. 早期基础能力与工程清理

| 文档 | 重点 |
|---|---|
| [2026-06-10-step1-cleanup.md](./2026-06-10-step1-cleanup.md) | 代码清理、共享 Retriever、路由层统一加载知识库 |
| [2026-06-10-step2-prompt-optimization.md](./2026-06-10-step2-prompt-optimization.md) | Chat、Diet、Search、Motion、MCP 的 Prompt 优化 |
| [2026-06-10-step3-knowledge-base.md](./2026-06-10-step3-knowledge-base.md) | 知识库补充和 RAG 内容建设 |
| [2026-06-10-step4-kb-chinese-verification.md](./2026-06-10-step4-kb-chinese-verification.md) | 中文知识库验证 |
| [2026-06-10-step5-tool-standardization.md](./2026-06-10-step5-tool-standardization.md) | `ToolResult`、错误码、工具输入校验和权限声明 |

### 2. 运行环境、协作与配置

| 文档 | 重点 |
|---|---|
| [2026-06-23-backend-port-startup.md](./2026-06-23-backend-port-startup.md) | 后端端口和启动记录 |
| [2026-06-23-codex-config-migration.md](./2026-06-23-codex-config-migration.md) | Claude 配置迁移到 Codex 协作配置 |
| [2026-06-26-git-two-computer-workflow.md](./2026-06-26-git-two-computer-workflow.md) | 两台电脑 Git 协作流程 |
| [2026-06-26-motion-runtime-dependencies.md](./2026-06-26-motion-runtime-dependencies.md) | Motion 图片姿态估计依赖、模型文件和 Conda 启动链路 |
| [2026-06-27-llm-memory-oom-fix.md](./2026-06-27-llm-memory-oom-fix.md) | 本地 LLM 重复加载导致 OOM 的根因和修复 |

### 3. 面试文档与文档结构

| 文档 | 重点 |
|---|---|
| [2026-06-23-interview-guide.md](./2026-06-23-interview-guide.md) | 面试手册整理 |
| [2026-06-25-interview-docs-reorganization.md](./2026-06-25-interview-docs-reorganization.md) | `interview/` 目录重组和专题目录划分 |
| [2026-06-26-docs-documentation-map.md](./2026-06-26-docs-documentation-map.md) | 新增 docs 文档地图 |
| [2026-06-30-interview-preparation-audit.md](./2026-06-30-interview-preparation-audit.md) | AI Agent 面试资料审查、基础优先原则和后续优化清单 |
| [2026-06-30-interview-study-material-reorganization.md](./2026-06-30-interview-study-material-reorganization.md) | `interview/` 收敛为 P0/P1/P2 分级背诵资料，原设计稿移动到 `technical/` |
| [INTERVIEW_PREPARATION_OPTIMIZATION_PLAN.md](./INTERVIEW_PREPARATION_OPTIMIZATION_PLAN.md) | 面试准备优化计划和完成状态，作为维护台账保留，不作为直接背诵材料 |

### 4. Router 演进

| 文档 | 重点 |
|---|---|
| [2026-06-24-router-weighted-rules.md](./2026-06-24-router-weighted-rules.md) | 从关键词路由升级到加权规则和路由元信息 |
| [2026-06-24-router-semantic-examples.md](./2026-06-24-router-semantic-examples.md) | 语义样例 fallback |
| [2026-06-24-router-eval-expansion.md](./2026-06-24-router-eval-expansion.md) | Router 评测集扩充 |
| [2026-06-24-router-eval-script.md](./2026-06-24-router-eval-script.md) | Router eval 脚本 |
| [2026-06-25-router-eval-mainstream-slices.md](./2026-06-25-router-eval-mainstream-slices.md) | 主流评测切片、primary intent policy |
| [2026-06-25-router-challenge-eval.md](./2026-06-25-router-challenge-eval.md) | 困难/失败样本集 |
| [2026-06-25-router-challenge-annotations.md](./2026-06-25-router-challenge-annotations.md) | challenge set 多意图标注 |
| [2026-06-25-router-llm-classifier-contract.md](./2026-06-25-router-llm-classifier-contract.md) | LLM classifier fallback 契约桩 |
| [2026-06-25-router-multi-intent-design.md](./2026-06-25-router-multi-intent-design.md) | multi-intent routing 设计 |
| [2026-06-26-router-phase3-roadmap.md](./2026-06-26-router-phase3-roadmap.md) | Router Phase 3 路线收口 |
| [2026-06-26-router-status-index.md](./2026-06-26-router-status-index.md) | Router 当前状态索引 |
| [2026-06-27-router-phase3-implementation.md](./2026-06-27-router-phase3-implementation.md) | Router Phase 3 分阶段实施和 A/B 记录 |
| [2026-06-30-router-phase4-implementation.md](./2026-06-30-router-phase4-implementation.md) | Router Phase 4 多意图识别、组合执行与结果合成实施记录 |

### 5. Motion 演进

| 文档 | 重点 |
|---|---|
| [2026-06-23-motion-api-and-interview-detail.md](./2026-06-23-motion-api-and-interview-detail.md) | `/motion/analyze` API 和面试讲解补充 |
| [2026-06-25-motion-media-pipeline-design.md](./2026-06-25-motion-media-pipeline-design.md) | Motion 媒体输入技术路线文档化 |
| [2026-06-25-motion-pose-sequence-schema.md](./2026-06-25-motion-pose-sequence-schema.md) | `PoseSequence` 中间格式 |
| [2026-06-25-motion-pose-estimator-adapter.md](./2026-06-25-motion-pose-estimator-adapter.md) | 姿态估计适配器 |
| [2026-06-26-motion-image-static-analysis.md](./2026-06-26-motion-image-static-analysis.md) | `/motion/analyze-image` 图片静态姿态分析入口 |

### 6. MCP、Web UI 与体验优化

| 文档 | 重点 |
|---|---|
| [2026-06-26-mcp-default-mock-fallback.md](./2026-06-26-mcp-default-mock-fallback.md) | MCP 默认 mock 与真实 server fallback |
| [2026-06-26-web-ui-chat-pending-state.md](./2026-06-26-web-ui-chat-pending-state.md) | Web UI 对话等待状态 |
| [2026-06-26-web-ui-motion-image-upload.md](./2026-06-26-web-ui-motion-image-upload.md) | Web UI Motion 图片上传入口和手工反馈修复 |

### 7. 测试语句与体验准备

| 文档 | 重点 |
|---|---|
| [2026-06-23-runtime-test-prompts.md](./2026-06-23-runtime-test-prompts.md) | 运行体验测试语句、服务启动和手工测试准备 |

## 保留原则

- 不删除单篇日期记录，它们是实现过程和面试追问时的证据。
- 当前真实状态以 `docs/README.md`、`docs/API.md` 和专题文档为准。
- 新增重要实现、修复、重构或文档结构调整时，继续追加日期记录，并把本索引同步补上。
- 如果变更影响当前能力、运行方式或面试口径，还要同步 `docs/README.md` 或对应专题文档。
