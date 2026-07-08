# GitHub 首屏与架构入口

## 问题

项目长期只有 `docs/README.md`，仓库根目录缺少 GitHub 自动展示的 README。外部阅读者需要先自行发现文档目录，也容易把独立 Motion 媒体 API 误解为 `/chat` Router 内部工具。

## 调整

- 新增根 `README.md`，集中展示定位、亮点、启动方式、验证层级、边界和文档入口。
- 使用 Mermaid 分开表示对话 Agent 与独立媒体 Motion API，避免架构口径混淆。
- 快速启动默认使用 LLM、Retriever 和 MCP 的本地演示模式，降低首次运行门槛。
- 首屏直接说明自动化测试中的 mock/skip 边界，不用总通过数替代真实效果。

## 影响

本次只增加文档入口，不改变运行行为。根 README 面向招聘方和首次访问者，详细事实仍由 `docs/README.md`、`docs/API.md` 和 `docs/RUNBOOK.md` 维护。
