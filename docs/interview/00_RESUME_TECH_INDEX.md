# P0 必须先看：简历技术点总表

这份文档只做一件事：把简历上出现过的技术点整理成面试可讲的索引。面试官通常不会按技术名词逐个考试，而是会围绕“你为什么用它、你怎么用它、它解决了什么问题、有没有替代方案、边界在哪里”来追问。

阅读方式：

1. 先掌握“必须会讲”的技术点，它们直接支撑个人健身助手 Agent 项目。
2. 再掌握“最好会讲”的技术点，它们能体现工程能力和实习经历。
3. 最后了解“了解即可”的技术点，防止被简历上的关键词问倒。

## 1. 必须会讲：健身 Agent 主线技术

| 技术点 | 它是什么 | 在简历项目里的作用 | 怎么用 | 类似方案 | 为什么选择 / 怎么讲取舍 |
|---|---|---|---|---|---|
| Python | 通用后端和 AI 工程语言，拥有成熟的模型、向量检索和数值计算生态。 | 作为健身 Agent 后端主语言，承接 LangGraph、RAG、Motion、MCP Client 等模块。 | 编写 API、Agent 编排、向量化、NumPy 动作算法、工具调用和测试脚本。 | Java、Go、Node.js。 | AI 生态完整、集成效率高；性能敏感模块可进一步拆分为独立服务。 |
| LLM | 大语言模型，擅长自然语言理解、规划、总结和表达。 | 负责理解用户意图、生成回答、改写搜索 query、解释动作分析指标。 | 不让 LLM 单独决定所有结果，而是让它结合 RAG、搜索、数值算法和工具结果输出。 | 传统规则系统、分类模型、模板系统。 | LLM 适合语言层任务，但不擅长精确计算和事实更新，所以必须结合工具。 |
| Agent | 会根据任务选择流程、工具和状态的大模型应用。 | 把健身问答、联网搜索、动作分析、饮食/菜谱工具调用组织成一个系统。 | 用户请求先进入 Router，再进入 Knowledge/RAG、Search、Motion、MCPTool 等子工作流。 | 单 Prompt 应用、传统后端规则系统、完全自主规划 Agent。 | 比单 Prompt 更可控，比完全自主 Agent 更稳定，适合健康类场景。 |
| LangGraph | 用图结构编排 Agent 流程的框架。 | 让多任务 Agent 的节点、状态、边显式化。 | 用 StateGraph 维护统一状态，Router 决定流向不同子工作流。 | 手写 if/else、LangChain Chain、AutoGen、CrewAI。 | 比 if/else 更清晰，比开放式多 Agent 更受控，方便讲架构和扩展。 |
| StateGraph | LangGraph 中基于共享状态流转的图。 | 支撑“路由层 + 执行层”的两级图结构。 | 每个节点读取/更新状态，例如 intent、messages、tool_result、final_answer。 | 普通函数调用链、状态机库。 | 对多子图和多意图流程更直观，也方便失败降级和调试。 |
| Router | 意图路由器，判断用户问题该进入哪个能力链路。 | 把用户请求分发到 Search、Motion、Knowledge、MCPTool。 | 根据关键词、规则、置信度、多意图组合和评测样本生成 route plan；Chat/Diet 对外可作为兼容意图，对内统一进入 Knowledge。 | LLM Router、embedding 分类、纯关键词 if/else。 | 先用确定性规则保证稳定和可解释，低置信样本再考虑 LLM fallback。 |
| 子工作流 / 子图 | 某一类任务的独立执行流程。 | Search、Motion、Knowledge、MCPTool 各自处理不同任务。 | 顶层 Router 选中后，把共享状态交给对应子流程执行；Knowledge 内部再区分 `general_qa` 和 `diet_advice`。 | 多工具函数、单体 handler。 | 子工作流比单纯工具更强调状态流、错误处理和多步执行。 |
| RAG | 检索增强生成，先检索资料，再让 LLM 基于资料回答。 | 负责健身健美领域知识问答，降低幻觉。 | 文档分块、embedding、相似度召回、过滤排序、注入 Prompt。 | 直接 Prompt、BM25、联网搜索。 | 稳定知识适合 RAG；最新信息交给 Tavily。 |
| Sentence-Transformers | 把文本编码成向量的语义模型库。 | 把健身知识 chunk 和用户问题转成 embedding。 | 文档和 query 都编码为向量，用 COSINE 做语义相似度检索。 | OpenAI Embeddings、bge、e5、Jina Embeddings。 | 本地可运行、成本低、适合原型；生产化可替换更强 embedding 模型。 |
| sentence-aware 分块 | 尽量按句子边界切分文本，而不是粗暴按字符截断。 | 让 RAG chunk 更完整，避免把一句话或一个知识点切碎。 | 先按句子/段落切，再控制 chunk 长度和 overlap。 | 固定长度切分、Markdown 结构切分、语义分块。 | 比固定字符切分更适合中文知识文档，原型成本低。 |
| embedding | 文本或数据的向量表示。 | 让“减脂晚餐怎么吃”和相关知识片段能通过语义相似度匹配。 | 文档入库时生成 embedding，查询时也生成 embedding，再做近邻搜索。 | 关键词倒排索引、人工标签。 | embedding 能处理同义表达，但要通过评测验证召回质量。 |
| Milvus | 向量数据库，负责持久化向量并执行近似最近邻检索。 | 承载健身知识 RAG 的向量存储与检索。 | chunk、embedding、source 写入 Collection，使用 IVF_FLAT + COSINE 检索 Top-K，并通过 nlist/nprobe 平衡召回与延迟。 | FAISS、Chroma、Qdrant、Elasticsearch/OpenSearch。 | 相比纯内存方案，Milvus 更适合持久化、索引管理和后续扩展；Retriever 接口保持上层无感。 |
| IVF_FLAT / ANN | IVF_FLAT 是一种近似最近邻索引；ANN 指近似最近邻搜索。 | 在 Milvus 方案中提升大规模向量检索效率。 | nlist 控制分桶，nprobe 控制查询多少桶，在召回和延迟间取舍。 | HNSW、FLAT、DiskANN。 | IVF_FLAT 好解释、适合面试讲清参数含义；不是回答质量的充分条件。 |
| COSINE 相似度 | 衡量两个向量方向是否相近的指标。 | 用于 query 与知识 chunk 的语义匹配。 | 对 embedding 归一化后计算余弦相似度，选 Top-K。 | L2 距离、内积 IP。 | 文本语义更关注方向，COSINE 是常用选择；最终要用 Recall@K 验证。 |
| 阈值过滤 / 去重 / 来源透传 | RAG 检索后的处理链路。 | 减少无关片段并保留回答依据。 | 低于阈值的结果丢弃；召回内容与 source 组成 `[RefN]` 证据块，去重后的 source 同时进入 API metadata。 | reranker、规则过滤、人工标签。 | 当前完成来源标识可追溯，不等于逐句 citation 已验证；生产化可引入 reranker 和 citation verifier。 |
| Tavily | 面向 LLM 应用的联网搜索 API。 | 负责最新健身信息、外部资料和时效性问题。 | Query Understanding -> Tavily Search -> Answer Synthesis。 | Bing Search API、SerpAPI、直接爬虫。 | Tavily 易接入且结果结构化，适合个人项目展示搜索链路。 |
| Query Understanding / query rewrite | 把用户口语问题改写成更适合检索或搜索的查询。 | 提升 Tavily 搜索召回质量。 | 提取核心实体、时间、目标和约束，生成搜索 query。 | 直接用原始问题、关键词抽取、LLM classifier。 | 原始问题常有口语和上下文，改写能提升稳定性，但要记录原 query 防止丢约束。 |
| Answer Synthesis | 把多个检索或搜索结果综合成最终回答。 | 让搜索结果变成结构化、可读、有来源约束的回答。 | 输入 title/content/url，输出总结、建议和来源。 | 直接返回搜索列表、模板拼接。 | 用户需要答案而不是结果列表，但要避免编造来源。 |
| 结构化画像校验 | 把 LLM 提取结果转换为受约束的数据模型。 | Diet 在检索和生成前处理身高、体重、性别、目标和偏好。 | 从模型文本提取 JSON，用 Pydantic 校验范围、枚举和长度；失败时使用未知画像并记录 warning。 | 直接使用 LLM 字符串、正则提取、Function Calling。 | 避免错误或恶意模型输出直接污染检索和推荐；仍需用户确认与隐私治理。 |
| Motion | 完整标准动作教练系统。 | 支撑图片/视频输入、姿态序列相似度分析、标准动作对比和教练式反馈。 | 媒体 API 将图片/视频转成 PoseSequence，再做归一化、DTW、余弦和 DTW 对齐逐关节平均距离；Motion 链路把数值结果转成可理解的动作指导。 | 只用 LLM 看图、规则阈值、训练动作分类模型。 | 没有大规模标注数据时，成熟姿态模型 + 可解释数值算法最适合原型验证；后续重点是扩展标准动作样本、动作周期切分和关节级专项阈值。 |
| MediaPipe Pose | Google 提供的预训练人体姿态估计方案。 | 把普通图片或视频帧转换为人体关键点，补齐 Motion 的媒体输入层。 | 图片使用 IMAGE 模式；视频由 OpenCV 抽帧后使用 VIDEO 模式和递增时间戳推理，输出 33 个关键点。 | MoveNet、RTMPose、YOLO-Pose、OpenPose。 | 本地运行、接入成本低且无需自行训练；复杂遮挡和专项精度不足时再替换模型。 |
| PoseSequence | Motion 内部统一姿态数据契约。 | 隔离媒体输入、姿态模型和下游分析算法，避免下游绑定 MediaPipe。 | 保存 `(T,J,C)` keypoints、fps、source_type、pose_model、joint_schema、confidence 和 metadata。 | 直接传 ndarray、模型原始结果、逐帧 JSON。 | 统一契约便于测试、持久化和替换上游模型，也兼容 `.npz`。 |
| OpenCV 视频抽帧 | 视频解码和帧采样工具。 | 控制视频推理量，把短视频转换成有限帧序列。 | 当前默认目标约 10 FPS、最多 300 个采样帧，并统计有效姿态帧比例。 | FFmpeg、PyAV、逐帧全量推理。 | OpenCV 接入简单；限量采样可以控制延迟和资源，生产化再补异步任务和硬件加速。 |
| 3D 人体姿态关键点 | 人体关节在每一帧的三维坐标。 | 把视频/图片中的人体动作转成可计算数据。 | 表示成 `(T, J, 3)`，T 是帧数，J 是关节点数，3 是 x/y/z；真实视频链路已验证 `mediapipe_33`。 | 2D 关键点、IMU 传感器、骨骼动作捕捉。 | 3D 比 2D 更能表达空间姿态，但对姿态估计模型、视角和数据质量有要求。 |
| `.npz` | NumPy 的压缩数组文件格式。 | 承载姿态关键点序列、标准动作和离线评测数据。 | 把 PoseSequence 的关键点与元数据落盘，Motion 模块读取后分析；普通用户可直接上传图片/视频。 | JSON、CSV、Parquet、数据库。 | `.npz` 适合本地数值数组和标准库，不再要求普通用户手工准备。 |
| NumPy | Python 数值计算库。 | 实现姿态归一化、角度计算、相似度指标。 | 用数组运算处理关键点序列。 | PyTorch、TensorFlow、纯 Python。 | NumPy 轻量、稳定，适合无训练的确定性算法；训练模型时再用 PyTorch。 |
| 姿态归一化 | 消除身高、站位、尺度差异对姿态比较的影响。 | 让动作相似度更关注动作本身。 | 中心化、尺度归一化、必要时做方向对齐。 | 原始坐标直接比较、相机标定、多视角重建。 | 原型阶段必要且成本低；生产化还要处理视角、遮挡和置信度。 |
| 关节角度 | 由三个关键点计算出的身体关节弯曲角。 | 后续让动作反馈落到膝、髋、肘等局部结构。 | 当前已实现通用三点夹角函数，但尚未接入公开媒体响应，也没有动作类型到关键关节和标准范围的映射。 | 直接比较坐标、训练分类器。 | 角度比坐标更符合健身动作语言；当前只能讲“算法原语已实现、专项规则待接入”。 |
| FastDTW / DTW 距离 | 比较两段时间序列相似度的算法，允许速度不同。 | 比较用户动作和标准动作的时序相似度。 | 对姿态序列或特征序列做时间对齐，输出距离。 | 标准 DTW、Soft-DTW、动作阶段切分。 | FastDTW 复杂度更低，适合原型；标准 DTW 更准确但更慢。 |
| 余弦相似度 | 衡量两个向量方向是否一致。 | 衡量归一化姿态特征整体方向是否相似。 | 把姿态或特征展开为向量后计算 cosine。 | L2 距离、皮尔逊相关。 | 和 RAG 中 COSINE 类似，直观且容易解释。 |
| 形状差异 | 时间对齐后对应关节位置的平均距离。 | 补充 DTW 和 cosine，衡量对齐后的全身结构偏差。 | 复用 FastDTW 路径，对每对对应帧计算逐关节欧氏距离，再取全局均值。 | Procrustes 分析、骨长约束、关节角规则。 | 当前只能说明总体偏差，不能回答具体哪个关节错误；阈值也需要正式样本校准。 |
| ReAct-inspired 状态流 | 借鉴 Reasoning + Acting，把推理、参数解析、工具执行和检查拆开。 | Motion 子图的 `think -> parse -> tool -> check`。 | 当前每次请求按固定边执行一次，不会根据观察结果回到 think/parse 继续自主规划。 | Function Calling、Plan-and-Execute、完整 ReAct 循环。 | 分阶段状态流便于观察和测试；准确口径是“借鉴 ReAct”，不是多轮自主 Agent。 |
| ToolResult / ErrorCode | 项目内部工具的统一返回结构和错误码。 | 让 Search、Retriever、Motion、MCP 等工具成功失败都能被子图稳定处理。 | 成功返回 `ok=True + data + meta`；失败返回 `ok=False + error_code + error_message`，错误码区分配置、网络、权限、参数、数据缺失和内部异常。 | 每个工具各自返回字符串、直接抛异常、HTTP 状态码散落处理。 | 统一结果契约比先做复杂 ToolRegistry 更实用，能先保证错误可观察、可降级、可测试。 |
| ToolRegistry | 工具元数据和执行治理中心。 | 已作为旁路治理层落地最小原型，用于统一工具注册、schema、权限、超时字段、重试、fallback 和 audit log。 | `ToolSpec(name, description, input_schema, permission, executor, timeout, retry, fallback)` 加 `register/list/validate/execute`；默认注册 `knowledge.retrieve`、`search.tavily`、`motion.compare_pose`、`mcp.call_tool` 四类代表工具。 | LangChain Tools、OpenAI Function Calling、MCP tools/list、自定义 if/else 调用。 | 当前不替代 LangGraph，也不让 LLM 自由发现和调用工具；主链路仍由子图控制，后续优先接入 Search。 |
| MCP | Model Context Protocol，模型应用连接外部工具的标准协议。 | 支撑外部菜谱/工具调用能力。 | 轻量 Client 已通过 JSON-RPC 发出 initialize、tools/list、tools/call，并解析首个 text content block；默认使用 mock。 | 直接 HTTP API、LangChain Tools、OpenAPI function calling。 | 当前没有完成响应 ID 校验、inputSchema 参数校验和真实 Server 兼容性验收，准确口径是“协议主链路原型”。 |
| JSON-RPC | 一种用 JSON 表达请求、响应和 id 的远程调用协议。 | MCP Client 与 Server 通信的基础形式。 | 当前请求会生成 UUID，但实现按 stdout 下一行读取响应，没有核对响应 id；只适合串行原型。 | REST、gRPC、WebSocket 自定义协议。 | 生产化需要 id 匹配、并发请求表、通知语义和协议错误校验。 |
| subprocess / stdio | 启动子进程并用标准输入输出通信。 | 本地拉起 MCP Server 并交换 JSON-RPC 消息。 | Python 启动 server command，stdin 写请求，stdout 读响应。 | HTTP 服务、消息队列、Unix Socket。 | 本地工具接入轻量，适合演示；生产化要补隔离、超时和权限。 |
| Sliding Window Memory | 只保留最近 N 轮对话的短期记忆。 | 控制历史长度并为 Knowledge 多轮问答和饮食建议提供上下文。 | deque 按 `user_id` 最多保存 6 轮；Knowledge 读取并注入最后 6 条消息（约 3 轮）。 | 全量历史、摘要记忆、向量长期记忆。 | 简单可控，适合面试项目的可运行版本；生产化还要考虑 Search、Motion、MCP 的跨能力记忆消费、认证、隐私和持久化。 |
| collections.deque | Python 双端队列。 | 实现固定容量滑动窗口。 | append 新消息，超过容量自动或手动淘汰旧消息。 | list、queue.Queue、Redis List。 | 两端操作 O(1)，比 list 头删更适合滑动窗口。 |
| Docker | 容器化工具。 | 体现项目部署意识，减少环境差异。 | 把后端依赖、启动方式、模型挂载、环境变量组织起来。 | 本地 venv/conda、Docker Compose、Kubernetes。 | 比纯本地脚本更可交付；个人项目不用夸大成生产集群。 |

## 2. 最好会讲：工程与实习技术

这些技术主要来自简历技能栏和实习经历。它们不一定都是健身 Agent 的核心，但能支撑“我有工程落地能力”的整体形象。

| 技术点 | 它是什么 | 简历场景 | 面试怎么讲 |
|---|---|---|---|
| TypeScript / JavaScript | 前端主力语言，TypeScript 在 JS 上增加类型系统。 | React 项目、小程序开发、前端实习。 | TS 能减少大型前端项目中的字段误用和接口不一致；JS 生态成熟，适合快速构建交互。 |
| React 18 | 前端 UI 框架。 | 云眸道路基础设施智能监测系统。 | React 适合组件化复杂界面；高频数据场景要控制 re-render，不能只会写页面。 |
| Zustand | 轻量 React 状态管理库。 | 低频无人机状态数据合并和分发。 | 比 Redux 更轻，适合中小型状态管理；复杂业务要设计状态粒度，避免全局状态导致无关刷新。 |
| MQTT | 发布订阅式消息协议，常用于 IoT。 | 无人机遥测数据实时订阅与分发。 | 适合设备数据实时上报；要区分高频/低频数据路径，避免前端主线程压力。 |
| lodash.merge | 深度合并对象的工具函数。 | 低频状态数据增量更新。 | 用于合并嵌套状态，减少全量替换；要注意引用变化导致的 re-render。 |
| PubSub 总线 | 发布订阅模式的事件分发机制。 | 高频 DRC 数据精准投递。 | 高频数据不适合全部进全局状态，PubSub 可以按订阅者精准分发。 |
| React Re-render 优化 | 控制组件不必要重复渲染。 | 拦截冗余渲染，保障高频数据不卡顿。 | 核心是状态拆分、选择器、memo、事件总线和渲染路径隔离。 |
| Mars3D / CesiumJS | 三维 GIS / 地球可视化引擎。 | 道路基础设施、无人机巡检、三维地图。 | 用于三维场景展示、轨迹、航线和空间数据可视化。 |
| WebRTC | 实时音视频通信技术。 | 无人机视频流直播。 | 适合低延迟直播；要关注连接状态、弱网、设备切换和流生命周期。 |
| Pointer Events API | 统一鼠标、触摸、触控笔输入事件的浏览器 API。 | 视频画面框选变焦、拖拽云台、双击瞄准、滚轮变焦。 | 比分别处理 mouse/touch 更统一，适合复杂交互。 |
| 归一化坐标 | 把屏幕坐标映射到 `[0,1]` 区间。 | 多分辨率视频画面交互。 | 让不同分辨率、不同窗口大小下的点击/框选语义一致。 |
| Generation Counter | 用递增版本号避免异步旧结果覆盖新状态。 | 设备快速切换时防止异步竞态。 | 每次切换生成新 generation，异步返回时只接受当前 generation 的结果。 |
| log/exp 映射 | 对数与指数映射。 | 指数级变焦滑块体验优化。 | 当物理量变化跨度很大时，用对数刻度让用户操作更线性。 |
| 键盘状态机 / Set | 用集合维护当前按下的键。 | 无人机多键组合操控。 | keydown/keyup 只更新状态，定时器统一汇总发送，避免事件频率不可控。 |
| 80ms 定时器 / 12.5Hz | 固定频率发送控制指令。 | 大疆 1024 协议杆量指令下发。 | 控制发送频率，避免弱网下指令堆积。 |
| TCP 队头阻塞 | TCP 按序传输导致前面包阻塞后面包。 | 弱网下控制指令堆积风险。 | 高频控制命令要限频、合并或丢弃过期指令。 |
| 小程序开发 | 微信生态轻量应用开发。 | 简历技能栏。 | 说明你不只会后端 Agent，也能把能力接到用户界面。 |

## 3. 了解即可：额外加分技术

| 技术点 | 它是什么 | 简历场景 | 面试边界 |
|---|---|---|---|
| Claude Code | AI 编程助手 / Agentic coding 工具。 | 简历技能栏中的 Agent 架构实践。 | 可以说了解其工具调用、上下文管理和代码修改流程，不要说成自己实现了 Claude Code。 |
| OpenClaw | Agent 架构实践相关项目/框架。 | 简历技能栏。 | 作为了解项，用来说明你关注 Agent 工程实践，不作为健身项目核心实现。 |
| RT-DETR | Transformer 系列实时目标检测模型。 | 论文中的轻量化目标检测。 | 它属于论文经历，不是健身 Agent 主线；可讲轻量化、参数量和 mAP。 |
| 轻量化目标检测 | 在尽量保持精度的同时降低模型参数量和计算成本。 | 水稻穗 UAV 图像检测论文。 | 面试 Agent 项目时不用主动展开，除非对方问论文或模型经历。 |
| UAV Imagery | 无人机航拍图像。 | 论文和实习场景都涉及无人机相关数据。 | 可作为“我接触过视觉和无人机数据”的补充，不要和 Motion 姿态估计混为一谈。 |
| mAP50 | 目标检测常用指标，IoU 阈值为 0.5 时的平均精度。 | 论文成果。 | 能说明检测模型效果，但和 RAG/Router 准确率不是一类指标。 |

## 4. 面试时的主线归纳

可以把简历技术压缩成三层：

| 层级 | 技术 | 面试表达 |
|---|---|---|
| Agent 控制层 | LangGraph、StateGraph、Router、ReAct、Memory | 我能把大模型应用组织成可控流程，而不是只写 Prompt。 |
| 工具与数据层 | RAG、Milvus、Sentence-Transformers、Tavily、MCP、NumPy、FastDTW | 我知道哪些问题该交给检索、搜索、协议工具或确定性算法。 |
| 工程交付层 | Python、Docker、React、TypeScript、Zustand、MQTT、WebRTC | 我能把 AI 能力落到可运行、可演示、可维护的工程系统里。 |

最稳的总结话术：

> 我的简历技术点可以归纳成三类：第一类是 Agent 控制层，比如 LangGraph、Router、ReAct 和 Memory，解决任务怎么流转；第二类是工具与数据层，比如 RAG、Milvus、Tavily、MCP 和 FastDTW，解决单纯 LLM 不能可靠完成的问题；第三类是工程交付层，比如 Python、Docker、React、TypeScript 和实时通信相关技术，保证系统能运行、能展示、能维护。这个项目最想体现的是：我不是只会调用模型，而是能把模型、工具、数据和工程边界组织成一个可解释的系统。
