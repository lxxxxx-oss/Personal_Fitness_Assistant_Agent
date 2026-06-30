# 文档脉络与阅读地图

本文档用于说明 `docs/` 目录下各类文档的职责、阅读顺序和维护思路。它不是新的项目说明，而是帮助快速判断“要看什么、改哪里、哪些内容只是历史记录”。

## 1. 总体脉络

当前 `docs/` 目录围绕一个核心目标组织：让项目既能真实运行，又能在面试中讲清楚“已实现能力、当前边界、后续演进和验证证据”。

可以把全部文档理解成五层：

```text
一线入口
  -> README.md / API.md / DOCUMENTATION_MAP.md / interview/PROJECT_INTERVIEW_GUIDE.md

二线专题
  -> interview/ / miniprogram/

三线证据
  -> progress/ / tests/

历史方案
  -> superpowers/
```

这套结构的核心思路是：

- `README.md` 回答“项目现在是什么状态，怎么运行”。
- `API.md` 回答“接口怎么调，协议是什么”。
- `interview/` 回答“面试时怎么讲，技术路线怎么解释”。
- `progress/README.md` 回答“这个能力是怎么一步步做出来的”，单篇日期记录作为证据保留。
- `tests/README.md` 回答“做完之后验证过什么，风险在哪里”，单篇测试记录作为证据保留。
- `superpowers/` 保留早期方案，不作为当前真实状态的唯一依据。

## 2. 推荐阅读顺序

如果是为了快速复习项目，建议按下面顺序读：

1. [README.md](./README.md)
   先建立项目全貌：能力范围、技术栈、当前进度、运行方式、已知问题和下一步优先级。

2. [interview/README.md](./interview/README.md)
   看面试材料的入口和专题分工，避免直接跳进长文档迷路。

3. [interview/PROJECT_INTERVIEW_GUIDE.md](./interview/PROJECT_INTERVIEW_GUIDE.md)
   作为主讲稿，重点读项目定位、三分钟讲法、五个子图、横切能力和高频问答。

4. [interview/SUBGRAPH_OPTIMIZATION_GUIDE.md](./interview/SUBGRAPH_OPTIMIZATION_GUIDE.md)
   理解后续优化路线，尤其是 RAG、Search、Motion、MCP、Router 的边界和演进。

5. [API.md](./API.md)
   对照当前接口，确认 `/chat`、流式接口、历史记录、Motion 上传接口和路由规则。

6. [tests/README.md](./tests/README.md)
   看验收矩阵，尤其是 Router eval、Motion 图片分析、Web UI 上传和 MCP fallback。

7. [progress/README.md](./progress/README.md)
   需要追溯某个能力的来龙去脉时按主题查找，不建议直接翻日期文件。

## 3. 目录职责

### 顶层文档

| 文档 | 作用 | 维护重点 |
|---|---|---|
| [README.md](./README.md) | 项目当前状态总入口 | 能力范围、进度、运行命令、配置、问题处理、下一步 |
| [API.md](./API.md) | 后端接口说明 | 请求/响应字段、流式协议、状态码、接口示例、路由规则 |
| [DOCUMENTATION_MAP.md](./DOCUMENTATION_MAP.md) | 文档阅读地图 | 文档结构、阅读顺序、维护边界 |

### `interview/`

`interview/` 是面试展示文档，不是普通开发文档。它的重点是把工程取舍讲清楚，并且始终区分“当前已实现”和“后续规划”。

| 文档 | 作用 |
|---|---|
| [interview/README.md](./interview/README.md) | 面试文档导航 |
| [interview/PROJECT_INTERVIEW_GUIDE.md](./interview/PROJECT_INTERVIEW_GUIDE.md) | 面试主讲稿、高频问答、代码讲解、边界说明 |
| [interview/SUBGRAPH_OPTIMIZATION_GUIDE.md](./interview/SUBGRAPH_OPTIMIZATION_GUIDE.md) | Chat、Search、Diet、Motion、MCP、Router 的优化总览 |
| [interview/motion/MOTION_MEDIA_PIPELINE_DESIGN.md](./interview/motion/MOTION_MEDIA_PIPELINE_DESIGN.md) | Motion 从 `.npz` 扩展到图片/视频输入的设计 |
| [interview/motion/MOTION_OPTIMIZATION_ROADMAP.md](./interview/motion/MOTION_OPTIMIZATION_ROADMAP.md) | Motion 分阶段路线和实际推进台账 |
| [interview/router/ROUTER_OPTIMIZATION_STATUS.md](./interview/router/ROUTER_OPTIMIZATION_STATUS.md) | Router 当前优化进度、评测基线和下一步 |
| [interview/router/MULTI_INTENT_ROUTING_DESIGN.md](./interview/router/MULTI_INTENT_ROUTING_DESIGN.md) | Router 从单 intent 演进到 multi-intent 的设计 |

### `miniprogram/`

`miniprogram/` 记录微信小程序端的设计、实施计划和完成度。

| 文档 | 作用 |
|---|---|
| [miniprogram/DESIGN.md](./miniprogram/DESIGN.md) | 小程序页面、组件、数据流、SSE 解析、API 适配设计 |
| [miniprogram/PLAN.md](./miniprogram/PLAN.md) | 小程序任务级实施计划 |
| [miniprogram/IMPLEMENTATION_STATUS.md](./miniprogram/IMPLEMENTATION_STATUS.md) | 小程序实现完成度和待联调事项 |

阅读口径：小程序代码已基本完成，但端到端联调仍是当前边界，不能说已经生产可用。

### `progress/`

`progress/` 是开发过程台账，按日期记录重要实现、修复、重构和文档整理。它的价值是给面试和复盘提供“演进证据”。

日常阅读优先看 [progress/README.md](./progress/README.md)，单篇日期记录只在追溯细节时打开。

主要可以按主题分组理解：

| 主题 | 代表文档 |
|---|---|
| 早期工程清理和基础能力 | `2026-06-10-step1-cleanup.md` 到 `2026-06-10-step5-tool-standardization.md` |
| 面试和运行文档整理 | `2026-06-23-interview-guide.md`、`2026-06-25-interview-docs-reorganization.md` |
| Router 优化路线 | `2026-06-24-router-*.md`、`2026-06-25-router-*.md`、`2026-06-26-router-phase3-roadmap.md` |
| Motion 媒体输入路线 | `2026-06-25-motion-*.md`、`2026-06-26-motion-*.md` |
| MCP 稳定性 | `2026-06-26-mcp-default-mock-fallback.md` |
| Web UI 体验 | `2026-06-26-web-ui-*.md` |
| 协作和环境 | `2026-06-26-git-two-computer-workflow.md`、`2026-06-26-motion-runtime-dependencies.md` |

维护原则：新增阶段性能力、重要修复或路线整理时，可以追加 progress 记录；不要把 progress 当成当前状态说明的唯一来源，当前状态要同步沉淀到 `README.md` 或专题文档。

### `tests/`

`tests/` 是验收和测试记录，证明项目不是只写了设计。

日常阅读优先看 [tests/README.md](./tests/README.md)，单篇测试记录只在需要查看命令、结果或遗留风险时打开。

| 类型 | 代表文档 |
|---|---|
| 早期冒烟和核心链路 | `2026-06-10-level-1-smoke-test.md`、`2026-06-10-level-2-core-link.md` |
| 手工体验语句 | `2026-06-23-manual-test-prompts.md` |
| Router 评测 | `2026-06-25-router-eval-and-challenge-test.md` |
| Motion 测试 | `2026-06-25-motion-*.md`、`2026-06-26-motion-image-static-analysis.md` |
| MCP fallback 测试 | `2026-06-26-mcp-default-mock-fallback.md` |
| Web UI 测试 | `2026-06-26-web-ui-*.md` |

阅读口径：`tests/` 记录“怎么验收过”，`progress/` 记录“怎么实现过”。两者最好配套看。

### `superpowers/`

`superpowers/` 保留早期方案和规格设计，属于历史源头，不应直接覆盖当前状态。

| 文档 | 作用 |
|---|---|
| [superpowers/specs/2026-06-09-fitness-assistant-design.md](./superpowers/specs/2026-06-09-fitness-assistant-design.md) | 早期设计规范 |
| [superpowers/plans/2026-06-09-fitness-assistant-plan.md](./superpowers/plans/2026-06-09-fitness-assistant-plan.md) | 早期任务级实现计划 |

阅读口径：这些文档适合解释“项目最初怎么规划”，但当前真实状态应以 `README.md`、`API.md`、`interview/` 和最新 progress/tests 为准。

## 4. 两条主线

### 主线一：项目能力从原型到可展示

这条线回答“项目到底做了什么”：

```text
早期设计
  -> 基础 LangGraph + FastAPI + RAG + 子图
  -> Router 从关键词升级为加权规则和语义样例
  -> Motion 从 .npz 分析扩展到 PoseSequence 和图片静态分析
  -> MCP 从真实 server 依赖调整为默认 mock + 真实 server fallback
  -> Web UI 增加等待状态和 Motion 图片上传入口
```

对应文档：

- `superpowers/`
- `progress/`
- `README.md`
- `API.md`
- `tests/`

### 主线二：面试表达从“做了功能”升级为“讲清工程取舍”

这条线回答“面试时怎么讲得新颖、真实、不虚”：

```text
项目定位
  -> 异构能力编排 Agent
  -> 可评测 Router
  -> Motion 算法工具链
  -> MCP 工具协议接入
  -> 流式输出和端侧体验
  -> 当前边界和后续路线
```

对应文档：

- `interview/PROJECT_INTERVIEW_GUIDE.md`
- `interview/SUBGRAPH_OPTIMIZATION_GUIDE.md`
- `interview/motion/`
- `interview/router/`

## 5. 文档维护准则

维护文档时先判断本次变更属于哪一类，再更新对应文档。核心原则是：当前事实写到一线文档，专题解释写到专题文档，过程和测试保留到索引化证据库。

### 5.1 什么时候必须维护文档

满足任一条件时，都要检查 `docs/`：

- 新增、删除或修改用户可见能力。
- 修改 HTTP、SSE、WebSocket、上传接口或响应字段。
- 修改 Router 意图分类、路由元信息、评测集或 fallback 策略。
- 修改子图流程、工具调用、状态字段、错误处理或降级策略。
- 修改运行方式、依赖、环境变量、模型文件、Docker 或两台电脑协作流程。
- 修改 Web UI 或微信小程序端入口、状态展示、交互流程。
- 新增或执行自动化测试、手工验收、冒烟测试。
- 做阶段性重构、Bug 修复、文档结构调整或面试口径调整。

小修小补如果不改变能力、接口、运行方式和面试口径，可以不新增 progress 记录，但仍应确认现有文档没有被变更影响。

### 5.2 文档分流表

| 变更类型 | 必须检查/更新 | 通常还要同步 |
|---|---|---|
| 项目定位、模块完成度、已知问题、下一步计划变化 | [README.md](./README.md) | [DOCUMENTATION_MAP.md](./DOCUMENTATION_MAP.md) 如果影响阅读路径 |
| 后端接口、请求/响应字段、状态码、SSE/WebSocket 协议、上传接口 | [API.md](./API.md) | `README.md` 的接口总览；相关 tests 记录 |
| Router 规则、语义样例、LLM fallback、route metadata、eval/challenge set | [interview/SUBGRAPH_OPTIMIZATION_GUIDE.md](./interview/SUBGRAPH_OPTIMIZATION_GUIDE.md) | [interview/router/](./interview/router/)、[progress/README.md](./progress/README.md)、[tests/README.md](./tests/README.md) |
| Chat/Search/Diet/Motion/MCP 子图流程或工具行为 | [interview/SUBGRAPH_OPTIMIZATION_GUIDE.md](./interview/SUBGRAPH_OPTIMIZATION_GUIDE.md) | `README.md` 当前状态、对应 progress/tests |
| Motion 媒体输入、PoseSequence、姿态估计、标准动作库、动作评测 | [interview/motion/](./interview/motion/) | `API.md`、`README.md`、Motion progress/tests |
| MCP server、mock/fallback、工具协议、进程生命周期 | `README.md`、[interview/SUBGRAPH_OPTIMIZATION_GUIDE.md](./interview/SUBGRAPH_OPTIMIZATION_GUIDE.md) | MCP progress/tests |
| Web UI 用户可见入口、上传体验、等待状态、错误展示 | `README.md` | Web UI progress/tests；必要时更新 API 使用说明 |
| 微信小程序页面、组件、API 封装、SSE 解析、联调方式 | [miniprogram/](./miniprogram/) | `README.md` 当前进度 |
| 运行命令、依赖、环境变量、模型路径、Docker、Conda | `README.md` | `progress/` 环境记录；必要时更新 `.codex/COMMANDS.md` |
| 面试主线、项目亮点、高频问答、诚实边界 | [interview/PROJECT_INTERVIEW_GUIDE.md](./interview/PROJECT_INTERVIEW_GUIDE.md) | `interview/README.md` 或专题文档 |
| 阶段性实现、重构、Bug 修复、文档结构调整 | [progress/](./progress/) 新增日期记录 | [progress/README.md](./progress/README.md) |
| 自动化测试执行、手工验收、冒烟测试、遗留风险 | [tests/](./tests/) 新增日期记录 | [tests/README.md](./tests/README.md) |
| 早期方案、旧计划、历史规格 | [superpowers/](./superpowers/) | 一般只保留，不作为当前状态事实源 |

### 5.3 一线事实源和二线证据

- `README.md` 是当前项目状态事实源：能力做到了哪里、怎么运行、还缺什么。
- `API.md` 是接口事实源：接口、字段、状态码、协议示例以这里为准。
- `PROJECT_INTERVIEW_GUIDE.md` 是面试表达事实源：怎么讲项目、怎么回答追问。
- `SUBGRAPH_OPTIMIZATION_GUIDE.md` 和专题目录负责技术路线：为什么这么设计、后续怎么演进。
- `progress/` 和 `tests/` 是证据库：记录过程和验收，不直接替代当前状态说明。

如果这些文档之间出现冲突，优先修正为：

```text
README/API 当前事实
  -> interview 面试表达
  -> progress/tests 过程和证据
  -> superpowers 历史方案
```

### 5.4 新增记录时的同步规则

新增 `docs/progress/YYYY-MM-DD-*.md` 后，要同步更新：

- [progress/README.md](./progress/README.md) 的主题索引。
- `README.md`，如果本次变更改变了当前进度、运行方式、配置或已知问题。
- 对应专题文档，如果本次变更改变了技术路线或面试口径。

新增 `docs/tests/YYYY-MM-DD-*.md` 后，要同步更新：

- [tests/README.md](./tests/README.md) 的验收矩阵。
- `README.md` 的测试结果，如果总测试结论或当前可展示能力发生变化。
- 对应 progress 记录，如果测试暴露出需要记录的问题修复过程。

### 5.5 不能写错的边界

- 不要把规划项写成已实现能力。
- 不要让 `progress/` 的历史记录覆盖 `README.md` 的当前事实。
- 不要让 `superpowers/` 的早期计划覆盖当前代码状态。
- 不要只改 API 不更新 Web UI 或小程序入口说明。
- 不要只记录测试通过，忽略遗留风险和未验证范围。
- 不要为了减少文档数量删除证据；优先新增索引或移动到二线阅读路径。
