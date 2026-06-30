# P2 了解即可：代码深挖与白板防守

这份文档用于面试官继续追问代码位置、数据结构、调用顺序和生产化方案时兜底。复习时先掌握 P0、P1，不要从这里开始背。

## 1. 简历技术点与代码入口

| 技术点 | 主要入口 | 能证明什么 |
|---|---|---|
| LangGraph Router | `app/graph/router.py` | 五 intent、受控多意图、错误隔离、结果合成 |
| 统一状态 | `app/graph/state.py` | 用户输入、记忆、路由和子图临时字段 |
| RAG | `app/tools/retriever.py` | 分块、Embedding、COSINE、阈值、Top-K、去重、关键词降级 |
| Search | `app/graph/subgraphs/search.py` | Query Understanding、Tavily Search、Answer Synthesis |
| MCP | `app/tools/mcp_client.py`、`app/graph/subgraphs/mcp.py` | JSON-RPC Client、工具发现/调用、真实与 mock 模式 |
| Motion | `app/tools/motion_tool.py`、`app/graph/subgraphs/motion.py` | 3D 姿态相似度与 ReAct 风格状态流 |
| PoseSequence | `app/tools/pose_sequence.py` | 不同姿态输入的统一中间结构 |
| 图片姿态 | `app/tools/pose_estimator.py` | 单帧关键点提取与置信度 |
| Memory | `app/memory/sliding_window.py` | `deque`、6 轮窗口、淘汰与清空 |
| FastAPI/流式 | `app/main.py` | REST、SSE、WebSocket、上传接口 |
| Router eval | `scripts/eval_router.py`、`data/eval/` | 绿色集与 challenge set 回归 |

## 2. 总体架构白板

```text
FastAPI /chat
  -> 读取 user_id 对应最近 6 轮 Memory
  -> LangGraph Router
       -> intent + confidence + reason
       -> optional secondary intents / route plan
  -> 执行层
       -> Chat: Retriever -> Prompt -> LLM
       -> Search: Rewrite -> Tavily -> Synthesis
       -> Diet: Profile -> Nutrition RAG -> Advice
       -> Motion: Think -> Parse -> Tool -> Check
       -> MCP: Discover -> Plan -> Execute -> Format
  -> 单结果返回，或白名单多结果合成
  -> 写回 Memory
```

讲图时先说控制面与执行面：Router 决定“去哪”，子图决定“怎么做”，Tool 完成具体原子动作。

## 3. 五条关键调用链

### 3.1 普通知识问答

```text
POST /chat
  -> _get_or_create_memory(user_id)
  -> graph.invoke(state)
  -> intent_classify_node
  -> Chat subgraph
  -> get_shared_retriever().search()
  -> retrieved chunks 注入 prompt
  -> LLMLoader.generate()
  -> memory.add_turn()
```

Shared Retriever 避免 Chat 与 Diet 分别加载同一套 Embedding 和知识库。

### 3.2 Tavily 联网搜索

```text
用户问题
  -> query_understanding_node
      -> LLM 改写为搜索关键词
  -> search_node
      -> TavilySearchTool.search(max_results=5)
      -> title/content/url
  -> synthesis_node
      -> 结果编号 + 来源 URL 注入 prompt
      -> _sources 收集 URL
      -> LLM 合成回答
```

代码边界：`_sources` 在 Router 内部能够随结果收集与合并，但普通 `/chat` 构造 `ChatResponse` 时目前没有显式传入该字段，所以 `sources` 仍使用默认空列表。

### 3.3 Motion ReAct

```text
think
  -> 判断用户要查看库、加载文件还是对比标准动作
parse
  -> 生成 _tools_to_call
  -> 更新 _iteration
tool
  -> load_npz_pose / compute_similarity
check
  -> 解释指标或说明缺失输入
```

当前条件边位于 parse 之后：有工具且未超过迭代上限时进入 tool，否则进入 check。tool 执行后直接进入 check，因此主要路径不是开放式无限循环。

### 3.4 MCP 工具调用

```text
discover
  -> MCPClient.connect()
  -> initialize
  -> notifications/initialized
  -> tools/list
plan
  -> LLM 或 mock 规则生成 {tool, arguments}
execute
  -> tools/call
  -> 解析 content block
format
  -> 工具结果转为用户回答
```

真实 Server 连接失败时，MCP 子图切换到 mock Client，并记录：

- `_mcp_mode`
- `_mcp_configured_command`
- `_mcp_fallback_reason`

### 3.5 SSE 流式输出

```text
POST /chat/stream
  -> graph.invoke(_streaming=True)
  -> 子图只准备最终 _prompt，不提前生成完整答案
  -> event: meta
  -> LLMLoader.generate_stream(prompt)
  -> data: token...
  -> 写入 Memory
  -> event: done
```

这避免“子图生成一次完整答案，接口再生成一次”的重复推理。WebSocket 使用相似思路。

## 4. Motion 算法深挖

### 4.1 输入验证

动作序列要求形状 `(T, J, 3)`，至少包含足够帧数和关键点，数据必须是有限数值。错误通过统一 `ToolResult` 和 `ErrorCode` 返回，而不是让 NumPy 异常直接穿透到 Agent。

### 4.2 归一化

核心目标：消除平移和尺度对相似度的干扰。

```text
原始关键点
  -> 以索引 0 的约定中心点做平移归一化
  -> 以全部关键点到中心点的平均距离做缩放
  -> 保留相对关节结构
```

生产化还可增加：朝向校正、左右镜像检测、低置信关键点插值、相机坐标标定。

### 4.3 FastDTW

将每一帧 `(J, 3)` 拉平成一维特征，比较两条时间序列。FastDTW 允许同一动作以不同速度完成，不要求第 10 帧必须和第 10 帧对应。

不能把 DTW distance 直接叫“准确率”。它是距离，阈值需要基于动作类别和真实样本标定。

### 4.4 多指标

| 指标 | 关注点 | 趋势 |
|---|---|---|
| DTW distance | 对齐后的时序轨迹差异 | 越小越接近 |
| cosine similarity | 归一化姿态方向一致性 | 越接近 1 越相似 |
| shape difference | 人体结构幅度序列差异 | 越小越接近 |
| joint angles | 局部关节几何 | 需按动作阶段解释 |

综合标签目前是工程阈值，不是经大规模运动科学数据验证的医学或教练结论。

### 4.5 从图片到视频

```text
video
  -> 固定 fps 抽帧
  -> 每帧姿态估计
  -> 置信度过滤、缺失点插值、平滑
  -> PoseSequence(T, J, 3)
  -> 动作阶段切分
  -> FastDTW + 多指标 + 专项规则
  -> 反馈
```

当前图片接口只完成 `T=1` 的第一部分，不能越级描述为完整视频动作分析。

## 5. RAG 与 Milvus 深挖

### 5.1 当前代码数据流

```text
data/knowledge/*.txt
  -> sentence-aware split (max 500 chars)
  -> SentenceTransformer.encode(normalize_embeddings=True)
  -> NumPy vectors
  -> query embedding
  -> dot product == cosine
  -> threshold
  -> sort
  -> Top-K
  -> content dedupe
  -> prompt context
```

Embedding 不可用时降级关键词搜索；返回 meta 中标明 `mode=embedding|keyword`，便于判断本轮不是同一种检索质量。

### 5.2 当前实现与简历 Milvus 口径

| 层级 | 当前仓库 | 简历/目标方案 |
|---|---|---|
| 文档分块 | 已实现 | 保留 |
| Embedding | Sentence-Transformers | 保留 |
| 相似度 | normalized dot product / COSINE | Milvus COSINE |
| 存储 | 进程内 NumPy | Milvus Collection |
| ANN 索引 | 无 | IVF_FLAT 或 HNSW |
| 后处理 | threshold、排序、Top-K、去重 | 保留，可增加 rerank |
| 元数据过滤 | 很轻 | source/topic/version/filter expr |
| 持久化与扩展 | 无 | Milvus 服务负责 |

面试时可以详细讲 Milvus 设计，但看到当前代码时必须明确右列是目标方案。

### 5.3 IVF_FLAT 白板

```text
build:
  embeddings -> k-means clusters (nlist) -> inverted lists

search:
  query -> nearest clusters (nprobe) -> exact distance in selected lists -> top-k
```

权衡：

- `nlist` 太小：每个桶过大，查询扫描多。
- `nlist` 太大：训练和管理成本上升，小数据还可能分桶不稳定。
- `nprobe` 大：召回更好但延迟更高。
- 数据很小：暴力 NumPy 检索往往更简单，未必更慢到值得部署 Milvus。

### 5.4 迁移接口

上层 Chat/Diet 目前只关心类似下面的结果：

```json
[
  {"content": "...", "score": 0.82, "index": 3}
]
```

Milvus 适配器应维持统一 `search(query, top_k, threshold) -> ToolResult` 契约，让子图不感知底层数据库变化。

## 6. MCP 协议深挖

### 6.1 为什么选择 stdio

本地 MCP Server 与 Agent 在同一机器时，stdio 不需要额外监听端口和鉴权服务，适合 CLI 工具和面试原型。缺点是进程生命周期、阻塞读写和 stderr 管理更复杂；远程生产服务更适合 HTTP transport、独立鉴权和连接池。

### 6.2 JSON-RPC 请求

典型请求包含：

```json
{
  "jsonrpc": "2.0",
  "id": "unique-id",
  "method": "tools/call",
  "params": {
    "name": "tool-name",
    "arguments": {}
  }
}
```

`initialize` 建立能力与版本上下文，`notifications/initialized` 是通知，不应期待普通结果；`tools/list` 返回描述与 input schema；`tools/call` 返回 content blocks。

### 6.3 当前错误处理

- Server 命令找不到：`DATA_NOT_FOUND`。
- 未连接调用：`NETWORK_ERROR`。
- 无响应或 JSON-RPC error：转换成 `ToolResult.fail`。
- 工具名为空、arguments 非字典：`INVALID_PARAM`。
- 真实配置连接失败：子图记录原因并回退 mock。

生产化缺口：完整 schema validation、请求级超时取消、进程健康检查、并发请求匹配、权限 allowlist 和审计。

## 7. Router 四阶段深挖

| 阶段 | 当前实现 | 价值 |
|---|---|---|
| Phase 1 | weighted rules、combo、pattern boosts | 快、可解释、可控 |
| Phase 2 | semantic examples、char n-gram Jaccard | 补隐式表达，不依赖模型 |
| Phase 3 | 可选 Qwen classifier、严格 JSON 契约 | 处理少量模糊样本，默认关闭 |
| Phase 4 | secondary intents、白名单组合、错误隔离、合成 | 支持受控复合任务 |

LLM classifier 默认关闭的核心原因不是“不会做”，而是 A/B 中没有带来足够正确率收益，却增加延迟和不确定性。面试里这是一项合理工程取舍。

## 8. 测试证据怎么讲

### 已覆盖

- FastAPI 参数与响应。
- Router 主流、困难和多意图样本。
- RAG 分块、排序、降级和参数错误。
- Motion 输入、相似度、PoseSequence 和图片适配。
- MCP mock 工具、请求结构和子图调用。
- Memory 容量、淘汰、读取与清空。
- 模型共享加载与部分错误路径。

### 未被这些测试证明

- 真实 Qwen 回答质量。
- 真实 Sentence-Transformer 的领域召回率。
- 真实 Tavily 每条结论的来源有效性。
- 真实 howtocook-mcp 的长期稳定性。
- Milvus 当前分支的直接集成。
- Motion 对真实用户动作的教练级准确性。
- Docker 跨机器完整构建与小程序真机体验。

## 9. 五分钟演示顺序

1. `/health`：证明服务启动。
2. `/ui` 普通知识问题：展示 Chat RAG 与 Memory。
3. 联网问题：展示 Search intent 和来源文本。
4. 菜谱问题：展示 MCP intent，并主动说明当前是 mock 还是真实 Server。
5. `/motion/analyze`：上传 `.npz` 并展示多指标。
6. Router eval：展示 66/66 和 36/36。
7. 收尾说明：Milvus、视频 Motion、真实来源校验是生产化重点。

演示前不要临时依赖没有验证的真实外部服务。稳定演示和明确模式，比现场赌网络更专业。

## 10. 生产化路线

优先级建议：

1. 建立 RAG 标准问答、Motion 标准动作和 Router 真实误判数据集。
2. 补全 Search 结构化来源透传与 citation validation。
3. 把视频转换成多帧 `PoseSequence`，再标定动作阈值。
4. 接入 Milvus 并以 Recall@K、P95 latency 对比 NumPy 基线。
5. 完善 MCP schema、超时、进程生命周期、权限和真实联调。
6. 把 Memory 迁移到 Redis/PostgreSQL，增加认证、TTL 和隐私删除。
7. 把本地模型拆成推理服务，再做 Docker 多环境验证。

## 11. 面试收尾

> 这个项目最有价值的地方，是把健身场景里不同性质的能力统一到一个受控 Agent 中：RAG 负责领域知识，Tavily 负责最新信息，NumPy/FastDTW 负责确定性动作计算，MCP 负责标准化外部工具调用，LangGraph 负责路由、状态和失败处理。我已经把原型链路、测试和演示入口打通，也清楚当前仓库与生产化方案的差异。下一步不是继续堆技术名词，而是用真实数据和指标把 Milvus、视频 Motion、来源校验和外部工具治理逐项做实。
