# P2 了解即可：代码深挖与白板防守

这份不用逐字背。目标是面试官打开代码继续追问时，你能准确说明调用链、实现细节、已知缺口和生产化方案。

## 1. 五条真实调用链

### 普通聊天

```text
POST /chat
  -> 根据 user_id 获取进程内 SlidingWindowMemory
  -> 构造 RouterState
  -> 同步 graph.invoke(state)
  -> intent_classify_node
  -> 一个或多个受控子图
  -> collect_route_result
  -> synthesize / finalize
  -> 保存对话历史
  -> 返回 intent + reply
```

注意：`/chat` 是 `async def`，但内部 graph 调用是同步的。

### SSE

```text
POST /chat/stream
  -> graph.invoke(_streaming=True) 准备最终 Prompt
  -> 先发送 meta(intent)
  -> 同步 generate_stream(prompt)
  -> 每取得一个 token 就 yield SSE data
  -> 保存完整回答
  -> done
```

准确口径：有增量 SSE 输出，但图执行和推理没有完全从事件循环隔离，也没有实现客户端断开后的生成取消。

### WebSocket

```text
/chat/ws
  -> 接收一次 user_id + message
  -> graph.invoke(_streaming=True)
  -> 在线程中执行 list(generate_stream(prompt))
  -> 等完整 token 列表生成后逐条发送 token 消息
  -> done
```

准确口径：消息协议已打通，但当前先缓存完整输出，不是真正实时生成一条发一条。

### `.npz` 动作序列分析

```text
POST /motion/analyze
  -> 分块保存上传的 .npz 临时文件
  -> load_npz_pose / PoseSequence 校验
  -> 可选加载 reference_name
  -> normalize + FastDTW + similarity
  -> 返回 frames / joints / metrics
```

聊天中的 Motion 子图也主要围绕 `.npz` 路径、标准动作库和相似度工具工作。

### 图片姿态提取

```text
Web UI 上传图片
  -> POST /motion/analyze-image
  -> 解码图片
  -> MediaPipe PoseLandmarker
  -> 单帧 PoseSequence
  -> 关键点数量和置信度摘要
  -> Web UI 展示
```

关键事实：这条路径直接由 FastAPI 调用 Pose Estimator，没有进入 LangGraph Motion 子图，也没有调用 FastDTW、标准动作对比或动作专项规则。

## 2. Router 四阶段的代码级口径

### Phase 1：Weighted Rules

实现：

- 每个 intent 有若干 `phrase -> weight`。
- 文本可以同时给多个 intent 累积分数。
- combo rule 和 pattern boost 处理跨词组合与边界表达。
- 根据最高分和分差计算工程置信度。

置信度是启发式映射，不是经过概率校准的真实概率。不要把 `0.85` 解释成“85% 正确率”。

### Phase 2：Semantic Examples

实现：

- 规范化文本后生成 token、字符 2-gram 和 3-gram 特征。
- 与人工样例计算 Jaccard 相似度。
- 用最佳分数和分差生成启发式 confidence。

它不是 Embedding 模型，也不是大规模语义检索；优点是离线、快速、可解释，缺点是对改写和长句泛化有限。

### Phase 3：LLM Classifier Fallback

实现：

- 只有 `LLM_ROUTER_ENABLED=true` 才调用本地 Qwen。
- 输出必须是合法 JSON。
- intent 必须在白名单内。
- `needs_clarification=true`、低于 0.70 或不高于已有确定性置信度时不会接管。
- 记录调用结果、选择结果和延迟指标。

A/B 结论：当前 challenge 样本没有新增正确项，却增加约 6.22 秒审查延迟，因此默认关闭。该结论不能推广到更强模型或真实线上样本。

### Phase 4：Controlled Multi-intent

实现：

- 使用中文标点和“然后、顺便、同时、再”等连接词切分子句。
- 子句继续走规则/语义分类，形成 observed secondary intents。
- 只有显式顺序表达才扩展 route plan。
- 只有四种两步组合允许执行。
- 每个子图由安全包装器捕获异常，成功结果最后统一合成。

当前缺口：

- `needs_clarification` 只记录状态并退回主意图，没有真的和用户多轮澄清。
- `chat -> search`、`diet -> mcp` 等很多合理顺序不在执行白名单。
- 规则中存在针对当前领域样本的人工修正，泛化依赖后续真实数据。

## 3. Motion 深挖

### Q：`.npz` 为什么存在？

> `.npz` 是姿态序列的内部持久化格式，不应要求普通用户理解。它让姿态估计层和动作分析层解耦：上游可以来自图片、视频或其他模型，下游只消费统一的 `T × J × C` 数据和 metadata。

### Q：为什么图片目前不能判断完整动作？

> 单帧只有一个时间点。它能观察关节位置、身体对齐和关键点置信度，但无法知道下降、最低点、上升、节奏、轨迹和重复稳定性。当前接口甚至还没有把单帧关键点送入动作专项角度规则，所以只能称为静态姿态提取和摘要。

### Q：FastDTW 和余弦相似度分别看什么？

> FastDTW 用于对齐不同速度或帧数的动作序列，距离反映时序轨迹差异；余弦相似度更关注归一化后姿态方向的整体一致性。两者都是统计相似度，不自动等于“动作标准”。要转成教练反馈，还需要动作阶段、关节角度阈值、左右侧规则和真实标注。

### Q：为什么不从零训练姿态模型？

> 这个项目的核心是 Agent 编排和动作工具链，不是姿态估计算法研究。使用 MediaPipe 这样的预训练模型更符合个人项目资源约束；个人工程工作集中在输入校验、模型适配、PoseSequence、分析接口和失败边界。

### Q：下一步如何真正形成视频动作分析？

```text
视频上传
  -> 文件大小/格式校验
  -> 解码和按 fps 抽帧
  -> 每帧 Pose Estimator
  -> 缺失点插值和置信度过滤
  -> PoseSequence
  -> 动作分段
  -> 角度、轨迹、节奏和标准序列对比
  -> 结构化问题与建议
```

## 4. RAG 深挖

### 当前数据流

```text
data/knowledge 文本
  -> sentence-aware chunk（约 500 字符）
  -> SentenceTransformer normalized embedding
  -> NumPy 向量矩阵

用户问题
  -> normalized embedding
  -> 点积/余弦相似度
  -> threshold 过滤
  -> Top-K
  -> Prompt 中的 Ref 片段
  -> LLM 回答
```

### 如果问 Recall@K

> 当前没有问题到证据片段的冻结标注集，所以没有可靠 Recall@K。我不会编数字。下一步会从知识库构造问题、标注支持片段，拆分开发集和留出集，再评估 Recall@K、MRR、无关片段率以及答案忠实度。

### 如果问怎么优化

1. 清理知识来源和版本。
2. 建立检索标注集。
3. 对比 chunk 粒度和 overlap。
4. 调整 Top-K 与 threshold。
5. 增加 BM25/关键词混合检索。
6. 加 reranker。
7. 返回结构化引用并验证 citation correctness。

不要把“迁移 Milvus”放在第一位。当前数据量很小，先解决数据与评测比替换数据库更有价值。

## 5. MCP 深挖

当前客户端验证的核心链路：

```text
解析 server command
  -> 启动 subprocess
  -> initialize
  -> notifications/initialized
  -> tools/list
  -> tools/call
  -> 提取 content
  -> ToolResult
```

可讲亮点：

- 不是直接导入一个菜谱 Python 函数，而是经过 stdio JSON-RPC 协议。
- 支持请求超时和 server 缺失降级。
- mock 使用与真实 server 相同的工具名称和结果入口，便于离线测试。

不能夸大：

- 没有证明对所有 MCP Server 兼容。
- 没有工具权限审批、用户确认和审计。
- 没有处理完整生命周期、复杂通知和多 transport。
- 默认 mock 的结果不能当作真实 MCP 集成成功证据。

## 6. 测试证据深挖

### 自动化测试覆盖

```text
API / Router / eval script
Retriever / LLM loader cache
MCP Client / Search Tool
Motion Tool / PoseSequence / Pose Estimator adapter
SlidingWindowMemory
```

测试策略：

- LLM 和 SentenceTransformer 全局 mock，保证离线和可重复。
- 外部搜索和 MCP 主要测 mock、失败和降级路径。
- MediaPipe 主要测输入、缺依赖、缺模型和伪造关键点转换。
- Router eval 使用真实确定性分类逻辑，但数据是项目自建回归样本。

因此可以说“自动化回归覆盖较完整”，不能说“真实端到端质量已经充分验证”。真正的端到端验收还要补：

- 真实 Qwen 回答抽样与评分。
- 真实 Embedding 的 RAG 检索集。
- 真实 Tavily 来源与引用校验。
- 真实 howtocook-mcp 兼容测试。
- 真实图片和视频动作数据集。

## 7. 生产化升级顺序

不要一次罗列十个技术名词。按风险和收益排序：

1. 认证、会话隔离、限流、输入和上传安全。
2. 结构化日志、trace id、Router/RAG/工具指标。
3. 拆独立模型服务，解决阻塞、并发和资源治理。
4. 建立 Router 留出集、RAG eval 和真实回答抽检。
5. 返回结构化来源并增加搜索内容安全处理。
6. Memory 迁移 Redis/PostgreSQL，并增加 TTL。
7. MCP 增加权限、用户确认、审计、超时和生命周期管理。
8. Motion 建真实标准动作库、视频管线和专项规则。
9. 数据规模增长后再决定是否迁移 pgvector/Milvus。

## 8. 白板题模板

### 当前架构

```text
Web UI / MiniProgram
  -> FastAPI
      -> /chat -> LangGraph Router
           -> Chat RAG
           -> Search
           -> Diet RAG
           -> Motion .npz Workflow
           -> MCP Tools
      -> /motion/analyze -> .npz Analysis
      -> /motion/analyze-image -> Pose Estimator -> Static Summary
  -> JSON / SSE / WebSocket protocol
```

这个图刻意把图片接口画在 LangGraph 之外，避免把“未来要串联”画成“当前已串联”。

### 生产化目标

```text
Client
  -> API Gateway / Auth / Rate Limit
  -> Agent Service
       -> Router + Trace
       -> RAG Service / Search
       -> Tool Gateway / MCP Permission
       -> Motion Service
  -> Model Serving
  -> Redis / PostgreSQL
  -> Metrics / Logs / Evaluation Pipeline
```

## 9. 五分钟演示顺序

1. 健身知识问题：展示 Chat 路由和回答。
2. 明确搜索请求：展示 Search 与 mock/真实状态。
3. 多意图白名单样本：展示 route plan，而不是宣称任意组合。
4. 上传图片：明确只展示关键点与静态摘要。
5. 展示 Router eval 报告和一条 mismatch 调试信息。
6. 主动展示一个 fallback，例如 MCP server 不存在后降级。

演示重点是“行为可解释、失败可控”，不是强行展示所有页面。

## 10. 面试收尾

> 这个项目最能代表我的地方，不是调用了多少模型，而是我把一个容易堆成 Demo 的 Agent 项目拆成了控制面、任务域、工具契约和评测证据。我也能指出它当前没有完成的部分：RAG 和 Motion 缺真实质量评测，流式和并发仍是单机原型，MCP 只覆盖核心子集。下一步会优先补真实数据闭环和运行治理，而不是继续堆功能。

## 11. 可以反问面试官

- 团队的 Agent 更偏开放式自主规划，还是受控 Workflow？如何定义二者的验收指标？
- 线上如何构建 Router、Tool Use 和 RAG 的持续评测数据？
- 模型推理是独立服务还是应用进程内调用？团队如何处理流式取消和资源隔离？
- MCP 或其他工具协议接入时，团队如何做权限审批和审计？
