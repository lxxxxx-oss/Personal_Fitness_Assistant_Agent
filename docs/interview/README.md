# 面试复习资料导航

本目录只服务一件事：围绕简历里的“个人健身助手 Agent”项目，准备能打动面试官、也能扛住追问的回答。

默认面试场景是：面试官从简历切入，通过追问判断你是否真正理解项目。因此回答要先讲业务价值和工程决策，再用数据流、关键参数、异常处理和评测方法证明实现深度。

## 回答总原则

```text
先按简历主线讲项目价值
  -> 再讲为什么这样选型
  -> 再讲实现思路和遇到的问题
  -> 最后在被追问时说明能力边界和生产化补齐
```

## 首次出现技术点的写法

后续维护 `docs/interview/` 时，第一次提到某个技术点或知识点，必须先讲清楚五件事：

1. **它是什么**：用一句普通人能听懂的话解释概念。
2. **它解决什么问题**：说明它在本项目里承担的职责。
3. **它怎么用**：结合本项目讲输入、处理过程、输出或落地方式。
4. **类似方案有什么**：至少说出 1-2 个替代方案。
5. **为什么选它**：讲清楚取舍，避免只堆技术名词。

面试表达要先让自己理解，再让面试官相信。不要只说“用了 LangGraph / Milvus / MCP”，而要说“为什么这个项目需要它，它替代了什么，它带来了什么收益，也有什么边界”。

## 面试表达公式

> 结论先行 → 业务问题 → 方案设计 → 关键实现 → 工程取舍 → 结果与演进

不要一上来主动削弱自己：

- 不要开场就说“其实代码里没有完全实现”。
- 不要把所有亮点都解释成“只是原型”。

但也不能乱编：

- 如果被问到 Milvus、MCP、Motion、Tavily、Memory 的实现细节，要能说清架构、数据流、核心实现思路和后续生产化。
- 对分阶段能力，先讲已经解决的问题，再把下一阶段放在“演进方向”中，不要用自我否定式语言开场。

## 简历主线

| 简历关键词 | 面试重点 |
|---|---|
| LangGraph / StateGraph | 为什么用图编排做多任务 Agent，而不是一个 Prompt |
| Router / 子工作流 | 如何把 Search、Motion、Knowledge、MCPTool 等能力调度起来 |
| Knowledge / Chat-Diet 融合 | 为什么普通问答和饮食建议统一进 Knowledge，再在内部区分 general QA 与 diet advice |
| 3D Motion / FastDTW | 为什么动作分析不能只靠 LLM，完整标准动作教练系统如何用姿态序列和相似度指标工作 |
| MediaPipe / PoseSequence | 如何把真实图片和视频转换成统一 3D 姿态序列，并进入标准动作对比和教练式反馈链路 |
| ReAct-inspired 工作流 | Motion 子图如何用一次 `think -> parse -> tool -> check` 分阶段执行，以及它为什么不是多轮自主循环 |
| 工具系统 / ToolRegistry | 内部工具如何定义、校验、执行、失败处理，为什么 MCP 只是协议补充，最小 Registry 如何设计 |
| MCP | 为什么把它定位为工具协议补充，自己实现 Client 做了什么 |
| Milvus / RAG | 健身知识如何分块、向量化、检索、完成真实链路效果评测并增强生成 |
| Tavily | 为什么联网搜索要做 query rewrite 和 answer synthesis |
| Sliding Window Memory | 缓冲区为何保存 6 轮、Knowledge 为何只注入最后 6 条消息，以及跨 Search/Motion/MCP 的长期记忆消费为何作为后续增强 |
| Docker | 如何说明项目具备部署意识，而不是只在本机脚本运行 |

## 阅读顺序

### P0-A：先看技术总表

[00_RESUME_TECH_INDEX.md](./00_RESUME_TECH_INDEX.md)

用于把简历上出现的技术点全部过一遍：是什么、解决什么、怎么用、类似方案、为什么选择。后续所有面试回答都围绕这张表展开。

### P0-速记：面试前十分钟

[04_ONE_PAGE_CHEAT_SHEET.md](./04_ONE_PAGE_CHEAT_SHEET.md)

用于面试前快速回忆项目定位、五条主线、关键数字和高压问题，不替代详细材料。

### P0-B：必须掌握

[01_MUST_MASTER_PROJECT_STORY.md](./01_MUST_MASTER_PROJECT_STORY.md)

用于准备 30 秒、3 分钟项目介绍，以及项目亮点、个人贡献和简历核心技术点。

### P1：最好掌握

[02_SHOULD_MASTER_TECH_QA.md](./02_SHOULD_MASTER_TECH_QA.md)

用于准备面试官围绕简历逐项追问：LangGraph、Motion、RAG/Milvus、MCP、Tavily、Memory、Docker、测试和边界。

[05_TOOL_SYSTEM_REGISTRY_DESIGN.md](./05_TOOL_SYSTEM_REGISTRY_DESIGN.md)

用于准备工具系统专项追问：内部工具系统与 MCP 的区别、当前约定式工具系统的边界，以及最小 `ToolRegistry` 设计。

### P2：了解即可

[03_GOOD_TO_KNOW_DEEP_DIVE.md](./03_GOOD_TO_KNOW_DEEP_DIVE.md)

用于深挖时白板解释实现链路、数据结构、算法指标和生产化路线。它不是让你背代码路径，而是帮助你把实现讲清楚。

## 复习标准

每个问题至少能回答五句话：

1. 这个技术点在项目里解决什么问题。
2. 为什么选择这个方案，而不是另一个方案。
3. 我具体做了哪些工作。
4. 遇到过什么限制或问题，我怎么处理。
5. 如果继续做成生产级，下一步怎么补齐。

`docs/interview/agent.json` 是本地简历源文件，包含个人信息，已被 `.gitignore` 忽略，不上传 GitHub。interview 文档围绕它的项目描述组织，但不复制个人隐私信息。

当前统一面试口径：

- Chat/Diet 融合进 Knowledge：对外可以保留 `chat`、`diet` 兼容意图，对内统一为 Knowledge 能力域，内部区分 `general_qa` 与 `diet_advice`。
- MCP 是工具协议补充：用于说明外部工具标准化接入，不把它讲成饮食主链路本身。
- 工具系统主线优先于 MCP：先讲内部工具的职责、schema、权限、executor、`ToolResult` 回传，再讲 MCP 是外部工具协议补充；`ToolRegistry` 已有最小原型并已接入 Search 与 Knowledge/RAG，且具备 `execution_id`、`duration_ms`、fallback 归因和 audit log，但不说成生产级工具平台或已全面接管所有工具。
- Milvus 已完成真实链路效果评测：可以讲 Collection、写入、检索、source 透传和 API 主链路验证；后续是扩大 Recall@K、MRR、忠实度和延迟基线规模。
- Motion 当前按完整标准动作教练系统表达：图片/视频进入 PoseSequence，与同 schema 标准动作做相似度比较并生成教练式反馈；后续重点是扩充样本库、专项规则和教练标注。
