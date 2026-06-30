# 文档阅读地图与维护边界

本页只负责导航和分流，不重复描述项目能力。当前状态看 [README.md](./README.md)，接口看 [API.md](./API.md)，运行命令看 [RUNBOOK.md](./RUNBOOK.md)。

## 1. 推荐阅读顺序

### 快速了解项目

1. [README.md](./README.md)：项目定位、架构、实现状态和边界。
2. [API.md](./API.md)：接口、字段和协议。
3. [tests/README.md](./tests/README.md)：测试结论和验收证据。

### 准备面试

1. [interview/README.md](./interview/README.md)：P0/P1/P2 阅读顺序。
2. [interview/01_MUST_MASTER_PROJECT_STORY.md](./interview/01_MUST_MASTER_PROJECT_STORY.md)：项目主线。
3. [interview/02_SHOULD_MASTER_TECH_QA.md](./interview/02_SHOULD_MASTER_TECH_QA.md)：技术追问。
4. [interview/03_GOOD_TO_KNOW_DEEP_DIVE.md](./interview/03_GOOD_TO_KNOW_DEEP_DIVE.md)：深挖兜底。

### 开发和排障

1. [RUNBOOK.md](./RUNBOOK.md)：启动、配置、测试和联调。
2. [technical/README.md](./technical/README.md)：Router、Motion 和历史设计资料。
3. [progress/README.md](./progress/README.md)：按主题追溯实现与修复过程。

## 2. 文档层级

```text
当前事实
  README.md / API.md / RUNBOOK.md

专题说明
  interview/ / technical/ / miniprogram/

过程证据
  progress/ / tests/

历史方案
  superpowers/ / technical/interview-archive/
```

发生冲突时，按以下优先级核对并修正：

```text
代码与自动化测试
  -> README / API / RUNBOOK 当前事实
  -> interview 面试表达
  -> technical 专题说明
  -> progress / tests 历史记录
  -> superpowers / archive 早期方案
```

历史记录用于说明当时发生了什么，不要求随着后续实现反复改写，但不能被当成当前状态入口。

## 3. 目录职责

| 位置 | 唯一职责 | 不应该承担 |
|---|---|---|
| `README.md` | 项目当前能力、边界、进度和下一步 | 大段运行命令、历史过程 |
| `API.md` | HTTP、SSE、WebSocket、上传接口事实 | 项目路线规划 |
| `RUNBOOK.md` | 安装、启动、配置、测试和联调命令 | 面试讲稿 |
| `interview/` | 基于实现、证据和边界的面试复习材料 | 开发台账、原始长设计稿 |
| `technical/` | 技术设计、专题状态和深挖材料 | 日常流水记录 |
| `miniprogram/` | 小程序设计、实施计划和完成度 | 后端通用说明 |
| `progress/` | 日期化实现、重构、修复和整理记录 | 当前状态的唯一事实源 |
| `tests/` | 测试执行、手工验收和遗留风险 | 自动化测试源码 |
| `superpowers/` | 早期规格和实施计划 | 当前实现状态 |
| `technical/interview-archive/` | 整理前的历史长文档 | 持续维护的专题事实 |

## 4. 修改分流

| 变更类型 | 必须检查 | 必要时同步 |
|---|---|---|
| 项目定位、能力状态、边界、下一步 | `README.md` | `interview/`、专题文档 |
| 请求/响应字段、状态码、流式或上传协议 | `API.md` | `README.md` 接口概览、相关 tests |
| 安装、启动、环境变量、模型文件、Docker | `RUNBOOK.md` | `README.md` 当前边界 |
| Router 规则、组合执行、评测策略 | `technical/router/` | `README.md`、interview、progress、tests |
| Motion 输入、PoseSequence、姿态估计和动作库 | `technical/motion/` | `API.md`、`README.md`、progress、tests |
| Web UI 用户入口和交互状态 | `README.md` | progress、tests、必要时 API |
| 小程序页面、组件、API 封装和联调 | `miniprogram/` | `README.md` |
| 面试主线、亮点和高频问答 | `interview/` | 确保不超出 README/API 当前事实 |
| 阶段性实现、重构或 Bug 修复 | 新增 `progress/YYYY-MM-DD-*.md` | 更新 `progress/README.md` |
| 自动化测试或手工验收 | 新增 `tests/YYYY-MM-DD-*.md` | 更新 `tests/README.md` |

## 5. 新增记录规则

新增 progress 记录时：

- 使用 `YYYY-MM-DD-topic.md` 命名。
- 写清变更概述、影响范围、验证结果、遗留问题和下一步。
- 同步加入 [progress/README.md](./progress/README.md) 的最近记录索引，并按“只保留最近 10 条”规则移除最旧记录。
- 如果改变当前能力或运行方式，同步更新 `README.md`、`API.md` 或 `RUNBOOK.md`。

新增 tests 记录时：

- 写清测试对象、命令或操作、结果和未验证范围。
- 同步加入 [tests/README.md](./tests/README.md) 的验收矩阵。
- 如果总测试结论或可展示状态变化，同步更新 `README.md`。

## 6. 不能写错的边界

- 不把规划项写成已实现能力。
- 不用历史 progress 或早期方案覆盖当前状态。
- 不把图片单帧分析说成视频动作时序分析。
- 不把默认 mock/fallback 说成真实外部服务始终可用。
- 不只写测试通过，还要保留未验证范围和遗留风险。
- `progress/` 只保留最近 10 条；需要长期保留的设计结论必须先沉淀到 `technical/`、`README.md`、`API.md` 或 `RUNBOOK.md`。
