# P1 最好掌握：技术追问与防守

这份材料不追求术语覆盖率，而是要求回答能够落到当前代码。先讲现状，再讲取舍，最后讲生产化方案。

## 1. Python、FastAPI 与并发

### Q1：项目为什么使用 `async`？当前实现真的非阻塞吗？

> FastAPI 的异步接口适合网络等待、SSE 和 WebSocket，但 `async` 不会自动让同步模型推理变快。当前 `/chat`、SSE 和 WebSocket 在 async 入口里仍会调用同步 `graph.invoke()`；SSE 也直接迭代同步的 `generate_stream()`。所以当前实现适合单机原型，不能说已经解决事件循环阻塞。生产化会把图执行和模型推理放到线程池、进程 worker、任务队列或独立模型服务，并增加取消和超时处理。

必须区分：

- I/O 并发：等待网络或文件时可以让出事件循环。
- CPU/GPU 推理：仍然是计算任务，需要隔离资源。
- `async def`：只是语法和调度入口，不等于内部调用非阻塞。

### Q2：SSE 和 WebSocket 有什么区别？项目分别做到哪里？

> SSE 是服务端到客户端的单向事件流，适合 LLM 文本增量输出，协议简单且浏览器支持好。WebSocket 是双向长连接，适合客户端也需要持续发送控制消息的场景。

当前实现：

- SSE 会在生成器产出 token 时逐步 yield，但图执行和模型生成仍是同步调用。
- WebSocket 已实现 meta/token/done/error 消息协议，但当前代码先在线程中把 token 全部收集成列表，再逐个发送，因此不是严格意义上的实时 token streaming。
- 生产化还要处理客户端断开、生成取消、背压、心跳、代理缓冲和超时。

### Q3：FastAPI 在项目里承担什么职责？

> FastAPI 是协议层，负责请求校验、HTTP/SSE/WebSocket、文件上传、状态码和静态页面；任务分发和业务流程交给 LangGraph、子图和工具。当前 API 层仍包含 Motion 上传处理等原型逻辑，生产化可以继续拆 service 层。

### Q4：本地模型并发如何处理？

> 当前通过进程级共享 tokenizer/model、首次加载锁和生成锁避免重复加载与并发踩踏。代价是同一进程的生成趋向串行，优先换取内存稳定。如果要提高吞吐，不应该简单增加 uvicorn worker 复制模型，而应拆独立推理服务并做动态 batching、队列和显存治理。

## 2. RAG 与回答可信度

### Q5：当前 RAG 具体怎么实现？

> 项目读取 `data/knowledge/` 中的文本，使用 sentence-aware 规则切分，单 chunk 约 500 字符；默认使用 `shibing624/text2vec-base-chinese` 生成归一化向量，通过 NumPy 点积计算余弦相似度。Chat 和 Diet 当前调用 Top-K 5、threshold 0.3；Embedding 加载失败时降级为关键词匹配。

诚实补充：配置中虽然存在 retriever 的 Top-K 和 threshold 字段，但当前 Chat/Diet 子图仍有硬编码参数，生产化前应统一配置入口。

### Q6：Embedding、Chunk、Top-K、Rerank 怎么解释？

> Chunk 决定知识的检索粒度；Embedding 把文本映射到向量空间；Top-K 控制候选数量；threshold 过滤低相关候选；Rerank 用更强模型对初召回结果重新排序。向量库只是存储与检索基础设施，不等于 RAG 效果本身。

### Q7：RAG 怎么评测？当前测了吗？

> 应分为检索和回答两层。检索看 Recall@K、MRR、命中率和无关片段比例；回答看上下文忠实度、完整性、引用正确性和拒答行为。当前项目还没有标准 RAG 问答集，因此不能给出 Recall@K，也不能宣称已经系统降低幻觉。现有测试主要验证 Retriever 的输入输出和降级逻辑。

### Q8：当前来源是否真的可追溯？

> Chat Prompt 会给检索片段编号，Search Prompt 会包含标题、内容和 URL，RouterState 也能保存部分 sources。但 `/chat` 当前没有把这些 sources 完整填入响应，SSE meta 也只返回 intent，所以来源暴露链路尚未完成。生产化要返回结构化 citation，并校验引用是否真的支持回答。

### Q9：如何降低幻觉和高风险健康建议？

> 不能承诺消除幻觉。可以约束回答基于检索上下文、资料不足时拒答、返回引用、对搜索内容做可信来源筛选，并给伤病和疾病场景增加专业咨询提示。还要避免在 Prompt 中把模型包装成真实注册营养师或医生；角色描述应是“提供一般信息的助手”，不能制造专业资质错觉。

## 3. Agent、Workflow、Tool 与 MCP

### Q10：Agent、Workflow、Chain 有什么区别？

> Chain 通常是固定步骤；Workflow 有显式状态、分支和错误路径；Agent 更强调根据任务动态选择行动。这个项目更准确的定位是受控 Agent Workflow：Router 可以选择任务域，但行动空间、组合顺序和最大范围由代码约束，不是开放式无限循环 Agent。

### Q11：为什么使用 LangGraph，而不是普通函数路由？

> 如果只有 `intent -> handler`，普通函数足够。这里使用 LangGraph 的原因是子图有多节点流程，多意图执行需要游标和结果集合，且要隔离子图错误并做最终合成。当前没有使用 checkpoint 持久化，因此 LangGraph 的价值主要是状态化编排和条件边，不应夸大为已经具备分布式恢复。

### Q12：Tool Schema 为什么重要？

> Schema 应清楚定义职责、输入、输出、权限和可处理错误。项目工具主要使用 `ToolResult` 和 `ErrorCode` 表达成功、错误码、消息、数据和 meta；这样子图可以区分配置缺失、输入错误、外部服务失败和降级结果。

### Q13：MCP Client 支持了什么？

> 当前是轻量 stdio JSON-RPC Client，完成了 subprocess 启动、initialize、initialized notification、`tools/list`、`tools/call`、超时读取和 mock 工具。它验证了工具发现到调用的核心链路，但没有覆盖完整 MCP SDK 能力、服务端请求、复杂通知、鉴权、权限审批、取消、审计和多 transport。

### Q14：为什么需要 mock fallback？

> 面试演示不能因为本机没有安装 howtocook-mcp 就让整条主流程崩溃，所以默认 mock 保证确定性演示；显式配置真实 server 时才尝试连接，失败后降级。必须在 UI、日志或响应 meta 中区分 mock 和真实结果，避免把演示数据冒充外部服务结果。

## 4. Router 与 Eval

### Q15：Router 当前怎么实现？

> 主意图先通过关键词和组合规则累计权重，低分或低置信时用字符 2-gram/3-gram 特征与示例做 Jaccard 相似度补充；LLM classifier 只有 feature flag 开启时才可能参与，并且要通过合法 JSON、允许意图、无需澄清、最低置信度和高于确定性结果等条件。Phase 4 再通过分句规则和领域信号生成 secondary intents 与 route plan。

不要把当前 Semantic Examples 说成 Embedding Router；它是轻量字符特征相似度。

### Q16：多意图路由是不是 Planner？

> 不是通用 Planner。当前主要依赖连接词分句、规则分类和少量领域修正规则；只有显式顺序表达才可能形成多步 route plan，执行层只允许 `search -> diet`、`search -> chat`、`motion -> chat`、`motion -> diet` 四种组合。其他组合保留观测信息，但退回主意图单路由。

当前 `needs_clarification` 只是状态和 warning：系统不会真正向用户发起一轮澄清对话。面试时应主动说明这是下一步，而不是已经实现的交互能力。

### Q17：66/66 和 36/36 如何解释？

> 两个集合共 102 条，覆盖五类 intent、边界冲突、多意图和顺序样本。它们由项目人工标注，并在 Router 演进过程中反复用于回归，因此指标是“当前规则对已知样本的回归结果”，不是独立泛化指标。下一步应把数据分为开发集和冻结留出集，再从真实日志中持续抽样复核。

### Q18：为什么 LLM Router 默认关闭？

> 本地 Qwen A/B 在当时 36 条 challenge 上保持了结果，但没有增加正确样本，平均每个被审查样本增加约 6.22 秒延迟。对控制面来说，这个收益不值得，所以默认关闭。这个结论只针对当前模型和数据，不代表规则永远优于 LLM。

## 5. 测试与证据

### Q19：114 个测试是什么性质？

> 这是 pytest 收集到的 114 个自动化用例，覆盖 API、Router、eval 脚本、Retriever、LLM Loader 缓存、MCP Client、Motion、PoseSequence、姿态适配器、搜索工具和记忆。为了离线、快速、可重复执行，测试全局 mock 了 LLM 和 SentenceTransformer，真实搜索、真实 MCP 和真实 MediaPipe 也大多通过 mock 或降级路径验证。

正确结论：

- 能证明确定性逻辑、契约和错误处理有回归保护。
- 不能证明真实 Qwen 回答质量、真实 Embedding 召回质量或外部服务稳定性。
- 真实模型 A/B、手工运行记录和自动化测试应该分开汇报。

### Q20：Router eval 为什么不直接算在普通单元测试里？

> 普通单元测试适合验证具体规则和边界；eval 脚本提供整体 accuracy、每类 precision/recall/F1、slice、混淆矩阵、source 分布和 mismatch，便于比较策略版本。测试可以调用 eval 保证绿色集不回归，但评测报告仍应独立保留。

## 6. Memory、可观测性与安全

### Q21：当前 Memory 是什么级别？

> 当前是进程内字典按用户提供的 `user_id` 保存 SlidingWindowMemory，默认 6 轮。它没有持久化、TTL、跨 worker 共享、用户认证或并发会话治理。生产化要把身份和会话绑定到认证体系，并迁移 Redis/PostgreSQL 等外部存储。

### Q22：Router 为什么说可解释？用户看得到吗？

> RouterState 内部记录 scores、confidence、source、reason、matches 和 route plan，eval 脚本也会统计 source 和 mismatch。但普通 `/chat` 响应只暴露 intent，当前还没有完整 trace API、持久化日志或监控面板。因此准确说法是“内部具备可解释元数据”，不是“已经完成生产可观测性”。

### Q23：当前安全边界有哪些？

> 当前是本地面试原型，没有认证、权限和限流，CORS 也较宽松。生产化至少要补：用户认证、会话隔离、速率限制、上传文件大小和 MIME 校验、Prompt Injection 防护、搜索内容隔离、MCP 工具权限、敏感日志脱敏和审计。

特别注意：

- 图片接口当前会一次性读取文件，应增加大小上限。
- 外部搜索结果和工具输出都是不可信输入，不能直接给予高优先级指令权限。
- 健康和饮食建议要有医疗边界，不能模拟真实资质。

## 7. 面试官高压追问

### Q24：你到底亲自写了什么，而不是调用库？

> LangGraph、MediaPipe、Tavily 和 Qwen 是基础能力。我亲自完成的是它们之间的控制面和工程胶水：Router 规则与元数据、eval 数据和脚本、状态和组合执行、错误隔离、MCP 轻量客户端、PoseSequence 适配层、接口与 UI 串联、共享模型加载和测试体系。我的创新不在于重新训练基础模型，而在于受控集成和可验证演进。

### Q25：如果去掉 LangGraph，项目还能运行吗？

> 可以用普通 Python 状态机重写，所以框架不是业务成立的必要条件。LangGraph 的收益是状态和边更显式、子图边界清楚、多步组合易扩展；代价是引入框架复杂度。当前规模下两种方案都能做，我选择 LangGraph 是为了展示和验证图式编排，而不是声称它是唯一答案。

### Q26：项目最薄弱的技术环节是什么？

> 当前最薄弱的是端到端质量证据：Router 有回归集，但 RAG、真实 LLM 回答、Motion 标准动作判断和真实 MCP 还缺冻结数据集与真实环境验收。下一步应该优先补数据和评测，而不是继续加新模块。

### Q27：如果只允许你生产化一个模块，先做哪个？

> 我会先把 Router、RAG 和 Chat 主链路生产化，因为它们有最高使用频率，也最容易建立真实数据闭环。先补认证、日志、引用、RAG eval、模型服务和会话持久化；Motion 和 MCP 保持受控实验入口，等数据和业务价值明确后再扩大。

## 8. 容易踩坑的说法

不要说：

- `async` 已经解决模型推理阻塞。
- WebSocket 已经真正实时逐 token 输出。
- Semantic Examples 是 Embedding Router。
- 多意图 route plan 是通用自主规划。
- 102 条满分证明线上泛化。
- 114 个测试证明真实模型和外部服务质量。
- 图片接口已经完成动作标准性判断。
- MCP 是完整生产级协议实现。

推荐说：

- 当前是单机受控原型，异步与模型服务仍需隔离。
- Router 指标是已知样本回归保障，泛化需要留出集和线上闭环。
- Motion 已完成输入适配和部分分析组件，图片、视频与完整动作判断尚未串联。
- MCP 实现核心工具链路，用于验证协议化接入和降级策略。
