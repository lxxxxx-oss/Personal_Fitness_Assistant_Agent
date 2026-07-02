# 面试前十分钟：项目一页速记

## 一句话定位

> 我构建了一个面向个人健身场景的多任务 Agent，用 LangGraph 组织“路由层 + 执行层”，把领域 RAG、实时搜索、3D 动作分析、饮食建议和 MCP 工具调用整合为可路由、可评测、可降级的系统。

## 30 秒介绍

> 顶层 Router 采用“加权规则 + 语义样例 + 可选 Qwen 兜底”，既识别单一意图，也能按白名单执行复合请求，并在 66 条常规样本和 36 条困难样本上持续回归。执行层中，Milvus RAG 负责领域知识，Tavily 负责实时信息，Motion 负责媒体到 3D 姿态序列及数值分析，MCP Client 负责标准化外部工具调用；最近 6 轮对话通过滑动窗口在任务之间共享。

## 五条主线

| 主线 | 一句话讲法 | 深挖关键词 |
|---|---|---|
| Router | 用确定性优先、模型兜底的混合路由平衡稳定性与语义覆盖 | StateGraph、权重、语义样例、route plan、白名单、66+36 |
| Milvus RAG | 把中文知识切块、编码、幂等写入 Milvus，再做 ANN 检索和后处理 | Schema、IVF_FLAT、COSINE、nlist/nprobe、Top-K、source |
| Motion | 把图片/视频统一成 PoseSequence，再执行可解释的时序和相似度计算 | MediaPipe、OpenCV、33 点、FastDTW、关节角、有效帧率 |
| Search | 查询改写、Tavily 检索、来源约束合成三阶段拆分 | title/content/url、source grounding、错误分类 |
| MCP | 自实现 Client 完成 Server 生命周期、工具发现和调用 | subprocess、stdio、JSON-RPC、initialize、tools/list、tools/call |

## 三个最能体现工程能力的点

1. Router 不凭感觉调规则：记录分数和原因，并用两套评测集持续回归。
2. LLM 不承担确定性计算：检索交给 Milvus，动作交给数值算法，外部工具交给 MCP。
3. 外部依赖失败不会拖垮全局：统一错误结构、子工作流隔离和可配置 fallback。

## 关键数字

| 数字 | 含义 |
|---|---|
| 66 + 36 | Router 常规样本与困难样本回归基线 |
| 最近 6 轮 | 滑动窗口短期记忆容量 |
| 33 个关键点 | MediaPipe Pose 的人体关键点数量 |
| 约 10 FPS / 300 帧 | 视频姿态提取的默认采样与资源上限 |
| IVF_FLAT + COSINE | Milvus 索引与相似度度量 |

## 五个高压问题

### 为什么不是普通聊天套壳？

> 因为系统会根据任务进入不同工作流，并调用检索、实时搜索、数值算法或协议工具；LLM 主要负责理解、规划和表达。

### 为什么 Router 不全交给 LLM？

> 高频明确意图用确定性规则保证稳定、低延迟和可解释；模糊样本再交给语义匹配或可选 Qwen，且所有策略都受离线评测约束。

### Milvus 做了什么？

> 它负责向量持久化、索引和 ANN 检索；我设计了固定 Schema、稳定主键、幂等 upsert、IVF_FLAT + COSINE，以及 Top-K、阈值、去重和来源返回。

### 视频能上传是否等于会纠错？

> 不等于。视频到 PoseSequence 解决输入问题；专业纠错还需要关键点平滑、动作周期、标准动作库和专项阈值。当前已经打通数据链路和通用相似度分析。

### 项目下一步做什么？

> 从功能建设转向质量闭环：RAG 做 Recall@K/MRR，Motion 建标准动作与教练标签，Search 做 citation 校验，MCP 补权限、超时和审计。

## 收尾句

> 这个项目的核心不是把技术名词放在一起，而是根据问题性质选择合适的执行者：LLM 负责语言，Milvus 负责知识检索，Tavily 负责实时信息，数值算法负责动作计算，MCP 负责外部工具，LangGraph 负责把它们组织成可控流程。
