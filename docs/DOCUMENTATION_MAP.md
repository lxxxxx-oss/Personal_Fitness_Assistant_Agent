# 文档导航

本页只回答“该看哪份文档”。项目能力以 [README.md](./README.md) 为准，接口以 [API.md](./API.md) 为准，命令以 [RUNBOOK.md](./RUNBOOK.md) 为准。

## 三个核心入口

| 需求 | 入口 | 内容 |
|---|---|---|
| 了解项目 | [README.md](./README.md) | 定位、架构、当前状态、边界、下一步 |
| 调用接口 | [API.md](./API.md) | HTTP、SSE、WebSocket、Motion 上传协议 |
| 运行排障 | [RUNBOOK.md](./RUNBOOK.md) | 安装、启动、环境变量、测试、Docker、联调 |

## 按场景阅读

### 面试准备

1. [一页速记](./interview/04_ONE_PAGE_CHEAT_SHEET.md)
2. [项目主线](./interview/01_MUST_MASTER_PROJECT_STORY.md)
3. [技术问答](./interview/02_SHOULD_MASTER_TECH_QA.md)
4. [深度追问](./interview/03_GOOD_TO_KNOW_DEEP_DIVE.md)

完整分级入口见 [interview/README.md](./interview/README.md)。

### 技术设计

- [technical/README.md](./technical/README.md)：专题索引。
- [Router 设计](./technical/router/MULTI_INTENT_ROUTING_DESIGN.md)：混合路由、复合任务与状态字段。
- [Motion 路线](./technical/motion/MOTION_OPTIMIZATION_ROADMAP.md)：PoseSequence、图片/视频和后续动作分析。

### 测试与过程

- [tests/README.md](./tests/README.md)：当前验收矩阵和关键证据。
- [progress/README.md](./progress/README.md)：最近开发记录索引。
- `progress/` 与 `tests/` 下的日期文件是历史证据，不是当前事实入口。

### 微信小程序

- [当前状态](./miniprogram/IMPLEMENTATION_STATUS.md)
- [设计参考](./miniprogram/DESIGN.md)
- [历史实施计划](./miniprogram/PLAN.md)

## 信息层级

```text
当前事实：README / API / RUNBOOK
    ↓
面试表达：interview/
    ↓
专题设计：technical/ / miniprogram/
    ↓
过程证据：progress/ / tests/
    ↓
历史方案：superpowers/ / technical/interview-archive/
```

发生冲突时，优先级为：

```text
代码与自动化测试
  > README / API / RUNBOOK
  > interview / technical
  > progress / tests 日期记录
  > superpowers / archive
```

## 维护规则

| 变更 | 必须更新 |
|---|---|
| 当前能力、边界、下一步 | `README.md` |
| 请求、响应、状态码、上传协议 | `API.md` |
| 安装、配置、部署、命令 | `RUNBOOK.md` |
| Router / Motion 设计 | 对应 `technical/` 专题 |
| 面试口径 | `interview/`，并与当前事实保持一致 |
| 阶段性开发或修复 | 日期化 `progress/` 记录及索引 |
| 自动化或手工验收 | 日期化 `tests/` 记录及验收矩阵 |

历史文档保留当时结论，不要求随功能演进反复改写；长期有效结论必须沉淀到核心入口或技术专题。
