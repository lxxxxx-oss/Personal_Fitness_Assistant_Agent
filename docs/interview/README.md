# 面试复习资料导航

本目录以 `agent.json` 中的简历项目描述为主线，目标是回答两类问题：简历亮点怎样讲得有吸引力，以及面试官追到代码时怎样把当前实现、原型取舍和生产化路径讲圆。

`agent.json` 包含个人信息，只在本地使用，已由 `.gitignore` 精确忽略，不上传 GitHub，也不在其他文档复制个人信息。

## 1. 回答原则

```text
先讲项目价值与个人贡献
  -> 再讲核心实现与选择原因
  -> 追问代码时说明当前仓库事实
  -> 最后给出生产化补齐路径
```

允许适当强化：

- 把零散实现组织成完整的“路由层 + 执行层”架构。
- 用目标技术方案说明系统如何生产化。
- 突出 Motion、MCP、RAG、Tavily、Memory 的组合价值。

不能制造低级矛盾：

- 当前仓库的 Retriever 是 NumPy 内存实现，不能说代码正在直接执行 Milvus IVF_FLAT。
- MCP Client 和真实协议路径已实现，但默认 `MCP_SERVER_COMMAND=mock`，不能把 mock 说成真实 Server 联调结果。
- Search 有来源数据、Prompt 引用和内部 `_sources`，但普通 `/chat` 还没有完整透传结构化 `sources`。
- 图片只提供单帧静态姿态，不能包装成完整视频动作判断。

## 2. 简历主线

| 简历关键词 | 面试重点 | 当前边界 |
|---|---|---|
| LangGraph / StateGraph | 多任务路由、子图、统一状态、组合执行 | 是受控工作流，不是通用自主 Agent |
| 3D Motion / FastDTW | 姿态归一化、关节角、时序对齐、多指标 | 主要输入为 `.npz` 时序；图片仅单帧 |
| ReAct | `think -> parse -> tool -> check`、最大迭代 | 当前主路径通常一次工具执行后检查 |
| MCP | stdio JSON-RPC、initialize、工具发现与调用 | 默认 mock 保证演示，真实 Server 需显式配置 |
| Milvus / RAG | 分块、Embedding、COSINE、阈值、去重、排序 | 当前仓库存储层为 NumPy，Milvus 是简历目标方案口径 |
| Tavily | query rewrite、搜索、来源约束合成 | 尚不是严格逐句 citation 系统 |
| 6 轮 Memory | `deque`、`user_id` 隔离、跨任务上下文 | 进程内短期记忆，不是长期持久化记忆 |

## 3. 阅读顺序

### P0：项目主线

[01_MUST_MASTER_PROJECT_STORY.md](./01_MUST_MASTER_PROJECT_STORY.md)

必须掌握：

- 一句话、30 秒和 3 分钟介绍。
- 四类业务能力与五条执行路径的关系。
- 七项个人贡献与三个主打亮点。
- Milvus、MCP mock、来源透传三个高压问题。

### P1：技术问答

[02_SHOULD_MASTER_TECH_QA.md](./02_SHOULD_MASTER_TECH_QA.md)

按简历逐项准备：

- LangGraph、Router 与 multi-intent。
- Motion、FastDTW、多指标与 ReAct。
- RAG、Sentence-Transformers、Milvus 和 IVF_FLAT。
- MCP Client、JSON-RPC、工具安全与 fallback。
- Tavily、来源、Memory、流式和模型治理。

### P2：代码深挖

[03_GOOD_TO_KNOW_DEEP_DIVE.md](./03_GOOD_TO_KNOW_DEEP_DIVE.md)

用于代码定位、调用链、白板题、测试边界、演示顺序和生产化路线。

## 4. 证据入口

| 想核对什么 | 文档 |
|---|---|
| 项目当前事实 | [../README.md](../README.md) |
| 接口与 Router 行为 | [../API.md](../API.md) |
| 启动和演示命令 | [../RUNBOOK.md](../RUNBOOK.md) |
| Router 设计 | [../technical/router/](../technical/router/) |
| Motion 设计 | [../technical/motion/](../technical/motion/) |
| 测试证据 | [../tests/README.md](../tests/README.md) |

历史长版材料位于 `docs/technical/interview-archive/`，只用于追溯，不作为当前面试口径。

## 5. 复习标准

不要逐字背答案。每个问题至少能说清：

1. 面试官为什么问。
2. 项目具体怎么做。
3. 为什么这样选。
4. 当前哪部分是原型或目标方案。
5. 如果继续做，如何验证升级真的有效。
