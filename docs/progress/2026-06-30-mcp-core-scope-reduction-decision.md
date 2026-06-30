# 2026-06-30 MCP 菜谱能力退出核心架构

## 操作类型

架构范围收敛 / 面试口径调整 / 后续代码迁移计划。

## 背景

项目核心目标是支撑面试展示。MCP 菜谱模块与 Diet 在“吃什么、怎么吃、具体菜谱”上职责重叠，当前实现又以 mock 为默认路径；继续把它作为核心亮点会增加协议学习、路由、配置、测试和面试防守成本。

## 本次决定

- 目标架构从 Chat、Search、Diet、Motion、MCP 五模块收敛为 Chat、Search、Diet、Motion 四个核心模块。
- 具体菜谱、食材搭配和餐单请求后续统一并入 Diet。
- MCP Client、`mcp` intent、MCP 子图、配置、评测样本和专项测试计划在下一次代码迭代中删除。
- MCP 作为早期工具协议实验保留在历史记录中，不再作为面试核心亮点。

## 本次实际修改

本次只更新文档，没有修改代码。当前仓库仍然可以返回 `intent=mcp`，114 条 pytest 和 66/36 Router 数据也仍包含 MCP 相关样本。

已更新：

- `docs/README.md` 和 `docs/API.md` 的当前状态与过渡说明。
- `docs/interview/` 的 P0/P1/P2 面试主线。
- `docs/technical/router/` 的 Router 状态和多意图设计说明。
- `docs/RUNBOOK.md` 与 `docs/miniprogram/` 的运行和端侧过渡说明。

## 后续代码迁移

1. 让 Diet 接管菜谱与食材请求。
2. 删除 Router 中的 `mcp` intent、规则、语义样例和边。
3. 删除 MCP 子图、Client、配置和 mock 菜谱实现。
4. 更新 Web UI 与小程序 intent 展示。
5. 重写 Router eval/challenge 标注并运行全量测试。
6. 更新 API、测试基线和面试数字。

## 风险

- 代码迁移前，文档必须同时说明“四模块目标架构”和“五 intent 当前实现”。
- 不能提前把 66/66、36/36、114 passed 当成删除 MCP 后的新基线。
- 菜谱并入 Diet 后要重新检查 diet-vs-recipe 样本，避免只是删除路由而没有补齐行为。
