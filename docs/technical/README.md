# Technical 文档索引

`docs/technical/` 用于保存技术设计、路线图、历史长文档和专题状态记录。这里的内容用于追溯细节和支撑面试追问，但不作为面试前直接背诵入口。当前面试主线以本地简历中的 LangGraph、Motion、ReAct、MCP、RAG/Milvus、Tavily 和 Memory 为核心，具体口径见 `docs/interview/`。

面试复习请优先阅读：

- [项目主线](../interview/01_MUST_MASTER_PROJECT_STORY.md)
- [技术问答](../interview/02_SHOULD_MASTER_TECH_QA.md)
- [深度追问](../interview/03_GOOD_TO_KNOW_DEEP_DIVE.md)

## 目录说明

| 目录 | 内容 |
|---|---|
| `interview-archive/` | 原完整面试手册、子图优化总览和阶段性面试优化计划，作为历史材料归档 |
| `router/` | Router 多意图设计、当前状态、评测基线和优化证据 |
| `motion/` | Motion 媒体输入、姿态估计、标准动作库和优化路线 |

## 当前专题入口

| 专题 | 设计 | 状态/路线 |
|---|---|---|
| Router | [多意图路由设计](./router/MULTI_INTENT_ROUTING_DESIGN.md) | [优化状态](./router/ROUTER_OPTIMIZATION_STATUS.md) |
| Motion | [媒体输入设计](./motion/MOTION_MEDIA_PIPELINE_DESIGN.md) | [优化路线](./motion/MOTION_OPTIMIZATION_ROADMAP.md) |

## 使用原则

- 复习背诵：看 `docs/interview/`。
- 查设计细节：看 `docs/technical/`。
- 查实现过程：看 `docs/progress/`。
- 查测试结果：看 `docs/tests/`。

如果 `technical/` 中的历史归档内容与当前代码或背诵资料冲突，以 `docs/README.md`、`docs/API.md`、`docs/interview/` 和最新 progress/tests 为准。
