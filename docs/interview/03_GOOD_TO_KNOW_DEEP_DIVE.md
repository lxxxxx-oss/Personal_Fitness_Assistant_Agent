# P2 了解即可：深挖与白板防守

这份文档用于面试官继续追问实现细节时兜底。注意：面试官通常看不到你的代码，所以这里不是背文件路径，而是准备白板级解释。

回答深挖问题时按这个结构：

```text
先画数据流
  -> 说明为什么这样设计
  -> 讲关键算法或协议
  -> 说清边界
  -> 给生产化升级方案
```

## 1. 总体架构白板

```text
User
  -> FastAPI API Layer
  -> LangGraph Router / StateGraph
       -> Chat RAG
       -> Search: Query Understanding -> Tavily -> Answer Synthesis
       -> Diet / Recipe
       -> Motion: Think -> Parse -> Tool -> Check
       -> MCPTool: Discover -> Plan -> Execute -> Format
  -> Memory: last 6 turns
  -> Response / Streaming
```

讲解重点：

- FastAPI 负责协议入口。
- LangGraph 负责状态和任务流转。
- Router 负责选择任务域。
- 子工作流负责具体能力。
- 工具负责确定性计算或外部服务。
- Memory 提供短期上下文。

## 2. Router 深挖

### 2.1 为什么需要 Router

健身助手的问题类型差异很大：

- 稳定知识：更适合 RAG。
- 最新信息：更适合 Tavily。
- 动作分析：需要姿态数据和数值算法。
- 菜谱工具：适合 MCP。

如果没有 Router，所有问题都丢给一个 Prompt，系统就很难稳定选择工具，也很难评测。

### 2.2 Router 演进思路

```text
关键词初筛
  -> 加权规则
  -> 组合规则与歧义处理
  -> 语义样例补充
  -> 可选 LLM fallback
  -> 多意图 route plan
```

面试口径：

> Router 是控制面，所以我优先选择确定性、可解释、可回归的策略。LLM 不是不用，而是放在低置信或复杂边界时作为 fallback。这样比完全交给 LLM 更稳定，也更容易定位错误。

### 2.3 多意图为什么受控

```text
用户说：先查最新建议，再给我饮食安排
  -> primary intent: search
  -> secondary intent: diet
  -> route plan: search -> diet
```

不要说它是通用 Planner。应该说：

> 当前是受控多意图路由，只支持常见白名单组合。这样能覆盖真实复合问题，同时避免任意组合导致不可测试、不可控。

## 3. Motion 深挖

### 3.1 数据结构

```text
PoseSequence
  frames: T
  joints: J
  coords: x, y, z
  metadata: fps, source, schema, confidence
```

为什么这样设计：

> 不管上游来自 `.npz`、图片还是未来的视频，最后都应该变成统一姿态序列。这样 Motion 算法层不依赖某一个姿态估计模型。

### 3.2 动作相似度流程

```text
3D keypoints
  -> center normalization
  -> scale normalization
  -> joint angle calculation
  -> FastDTW temporal alignment
  -> cosine similarity
  -> shape difference
  -> LLM explains metrics
```

每个指标怎么讲：

- **关节角度**：看局部动作结构，例如膝、髋、肘的弯曲程度。
- **FastDTW**：处理两段动作速度不同、帧数不同的问题。
- **余弦相似度**：看整体姿态方向是否一致。
- **形状差异**：看人体结构变化幅度是否接近。

### 3.3 图片与视频边界

单张图片：

```text
能做：静态关键点、姿态置信度、局部角度参考
不能做：完整动作轨迹、节奏、重复稳定性
```

视频路线：

```text
video
  -> frame sampling
  -> pose estimation per frame
  -> confidence filtering
  -> interpolation
  -> PoseSequence(T > 1)
  -> phase segmentation
  -> similarity + rule feedback
```

面试口径：

> 我不会说单张图片能完整判断动作标准。完整动作判断需要视频序列、标准动作库、阶段识别和阈值标定。当前项目先验证姿态序列和相似度算法链路，这是性价比更高的原型路线。

## 4. RAG 与 Milvus 深挖

### 4.1 RAG 数据流

```text
documents
  -> sentence-aware chunk
  -> Sentence-Transformer embedding
  -> vector store / Milvus target
  -> COSINE search
  -> threshold + Top-K
  -> dedup + ranking
  -> grounded prompt
  -> answer
```

### 4.2 Milvus 在哪里发挥作用

Milvus 主要替换的是向量存储和近似最近邻检索层：

```text
原型层：in-memory vectors
生产层：Milvus Collection + index + search params
```

Collection 可以包含：

- `id`
- `chunk_text`
- `embedding`
- `source`
- `topic`
- `version`
- `created_at`

### 4.3 IVF_FLAT 怎么讲

> IVF_FLAT 会先把向量聚成多个倒排桶。查询时不扫全量向量，而是只搜索最接近的若干桶。`nlist` 控制分桶数量，`nprobe` 控制查询时搜索多少桶。nprobe 越大，召回通常越高，但延迟也越高。

注意：

> IVF_FLAT 解决的是检索性能和召回权衡，不直接保证回答质量。回答质量还取决于知识库、chunk、query、rerank 和 prompt。

### 4.4 RAG 评测

```text
Retrieval:
  Recall@K
  MRR
  hit rate
  irrelevant chunk ratio

Generation:
  faithfulness
  answer relevance
  citation correctness
  refusal when no evidence
```

面试口径：

> 我不会只说“接了 Milvus”。真正的 RAG 优化要先有评测集，再比较 chunk、Top-K、threshold、reranker 和向量库配置。

## 5. MCP 深挖

### 5.1 MCP 调用链

```text
Agent
  -> start MCP Server by subprocess
  -> initialize
  -> notifications/initialized
  -> tools/list
  -> choose tool + arguments
  -> tools/call
  -> parse content block
  -> ToolResult
```

### 5.2 为什么用 stdio

> 对本地工具和 CLI Server 来说，stdio 不需要额外监听端口，适合原型和本地集成。缺点是进程生命周期、阻塞读写和 stderr 管理更复杂。生产化远程工具更适合 HTTP transport、鉴权和连接池。

### 5.3 安全边界

不能让 LLM 任意执行系统命令。需要：

- Server 命令来自配置。
- 工具名来自 tools/list。
- 参数做 schema validation。
- 工具 allowlist。
- 超时和进程隔离。
- 审计日志。

## 6. Tavily 搜索深挖

### 6.1 三阶段

```text
Query Understanding
  -> Tavily Search
  -> Answer Synthesis
```

为什么这样拆：

- Query Understanding 提高搜索词质量。
- Search 返回结构化结果。
- Synthesis 把来源和要点组织成用户能读懂的回答。

### 6.2 来源边界

可以说：

> 搜索结果的标题、摘要和 URL 会进入回答链路，回答生成时会受到来源约束。

不要夸大：

> 不要说已经完成逐句 citation verifier。生产化还要做引用校验、来源可信度分级和结构化返回。

## 7. Memory 深挖

### 7.1 为什么是滑动窗口

```text
new message append right
old message pop left
```

`deque` 两端操作是 O(1)，适合固定窗口记忆。

### 7.2 为什么是 6 轮

6 轮是折中：

- 太短：丢上下文。
- 太长：token 成本高，噪声多。
- 可配置：生产化可按场景调整。

边界：

> 这是短期上下文记忆，不是长期用户画像。长期记忆需要认证、持久化、脱敏、删除和跨实例共享。

## 8. 测试与评测深挖

测试能证明：

- Router 规则没有回归。
- API 契约能跑通。
- 工具错误能被处理。
- Motion/RAG/MCP 的核心函数有保护。

测试不能证明：

- 真实 LLM 回答质量。
- 真实 Tavily 来源可靠性。
- RAG 真实召回率。
- Motion 专业教练级准确性。

面试口径：

> 测试和 eval 是工程回归证据，不是生产效果证明。生产化还需要真实数据集、人工标注和线上日志闭环。

## 9. 生产化升级路线

优先级建议：

1. 建立 RAG 问答评测集和 Motion 标准动作数据。
2. 把 Router 线上误判样本沉淀成新 eval。
3. 接入 Milvus，并用 Recall@K 和 P95 latency 对比原型基线。
4. 视频 Motion：抽帧、姿态估计、动作阶段划分、规则反馈。
5. MCP：真实 Server 部署、schema validation、权限、超时、审计。
6. Tavily：来源可信度、citation 校验、缓存和熔断。
7. Memory：Redis/PostgreSQL 持久化、认证和隐私治理。
8. Docker：模型资产、环境变量、健康检查和日志。

## 10. 白板收尾

> 这个项目最有价值的地方，是把健身场景里不同性质的能力统一到一个受控 Agent 中：RAG 负责稳定知识，Tavily 负责最新信息，FastDTW 和数值指标负责动作计算，MCP 负责外部工具标准化，LangGraph 负责路由、状态和失败处理。它不是为了堆技术名词，而是展示我如何做任务拆分、工具编排、评测和工程边界控制。
