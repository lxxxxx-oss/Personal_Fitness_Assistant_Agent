# Progress 最近记录

`docs/progress/` 保存日期化实现、修复和文档调整记录。本页只索引最近 10 条，避免导航继续膨胀；未列出的旧文件作为历史证据保留。当前项目状态仍以 [../README.md](../README.md) 为准，测试证据看 [../tests/README.md](../tests/README.md)。

保留规则：

- 索引按完成时间倒序展示最近 10 条；同一天按实际完成顺序排列。
- 新增记录时从索引移除最旧条目，但不要求删除历史文件。
- 长期有效的设计结论沉淀到 `technical/`，接口和运行事实沉淀到 `API.md`、`README.md` 或 `RUNBOOK.md`。
- progress 是近期过程记录，不承担长期档案库职责。

## 最近 10 条

| 日期 | 记录 | 重点 |
|---|---|---|
| 2026-07-09 | [Knowledge 接入 ToolRegistry](./2026-07-09-knowledge-tool-registry-integration.md) | Chat/Diet 的 RAG 检索通过 `knowledge.retrieve` 接入 Registry，并完成全量回归 |
| 2026-07-09 | [ToolRegistry 可观测性](./2026-07-09-tool-registry-observability.md) | Registry 结果和 audit log 增加 `execution_id`、`duration_ms`、attempts 和 fallback 归因 |
| 2026-07-09 | [Search 接入 ToolRegistry](./2026-07-09-search-tool-registry-integration.md) | Search 子图通过 `ToolRegistry.execute("search.tavily")` 调用工具，并完成全量回归 |
| 2026-07-08 | [Diet 结构化画像校验](./2026-07-08-diet-profile-validation.md) | Pydantic 校验画像范围与枚举，非法 LLM 输出安全降级并公开 warning |
| 2026-07-08 | [同步 LangGraph 与流式生成异步桥接](./2026-07-08-async-graph-and-stream-bridge.md) | 三种协议在线程执行同步图，SSE/WS 共用非阻塞 token queue |
| 2026-07-08 | [RAG 来源透传闭环](./2026-07-08-rag-source-propagation.md) | Chat/Diet 共用编号证据格式，并将知识来源透传到三种协议 |
| 2026-07-08 | [Motion 指标语义与坐标空间加固](./2026-07-08-motion-metric-semantics-hardening.md) | 形状差异改为 DTW 对齐逐关节距离，并拒绝已知坐标空间冲突 |
| 2026-07-08 | [本地原型安全与部署边界](./2026-07-08-local-prototype-security-boundary.md) | 明确无鉴权、CORS、内存会话和 liveness/readiness 边界 |
| 2026-07-08 | [GitHub 首屏与架构入口](./2026-07-08-root-readme-and-architecture.md) | 新增根 README，用 Mermaid 区分对话 Agent 与独立媒体 API |
| 2026-07-08 | [测试与真实依赖边界审计](./2026-07-08-test-and-dependency-boundary-audit.md) | 区分 mock 自动化、真实依赖验收和 MCP 协议原型边界 |

## 维护方式

新增记录必须写清：变更概述、影响范围、验证结果、遗留问题和下一步。记录完成后，同时检查：

- 是否需要更新 `docs/README.md` 的当前状态。
- 是否改变 `docs/API.md` 的接口事实。
- 是否改变 `docs/RUNBOOK.md` 的运行方式。
- 是否需要在 `docs/tests/` 增加验收记录。
