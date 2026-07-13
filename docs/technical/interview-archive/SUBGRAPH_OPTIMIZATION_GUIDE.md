# 子图优化方向汇总

> 归档说明：本文是整理前的子图优化长文档，保留用于追溯历史路线和设计细节。当前面试复习请优先使用 `docs/interview/` 下基于实现、证据和边界整理的 P0/P1/P2 材料；专题设计以 `docs/technical/router/`、`docs/technical/motion/` 和最新 progress/tests 为准。

本文档保留整理前各个 LangGraph 子图的优化思路，方便追溯历史路线。它不再承担当前状态维护职责。

原则：

- 区分“当前已实现”和“后续可优化”，不要把规划项说成已落地。
- 优化方向尽量对应可验证指标，而不是只写“效果更好”。
- 后续 Router 和 Motion 的当前状态分别维护在 `docs/technical/router/`、`docs/technical/motion/`；其他模块的当前事实以 `docs/01_项目总览.md`、最新 progress/tests 和代码为准。

## 1. Chat / Diet RAG 优化方向

Chat 子图和 Diet 子图都依赖共享的 `MemoryRetriever`，因此 RAG 优化可以放在一起考虑。

当前实现：

- 知识库来自 `data/knowledge/` 下的本地 `.txt` / `.md` 文档。
- 当前知识内容包括健身基础、力量训练、营养、WHO 健康饮食、WHO 身体活动、CDC 力量训练等资料。
- 启动时由 `load_shared_knowledge_base()` 加载文本。
- 文档通过 `_chinese_sentence_split()` 做 sentence-aware 分块，默认每个 chunk 控制在约 500 字符以内。
- 使用 Sentence-Transformers 编码 chunk，并开启 `normalize_embeddings=True`。
- 检索时用 NumPy 点积计算余弦相似度。
- 使用 `threshold=0.3` 做低相关过滤。
- 使用 `top_k=5` 控制注入 Prompt 的上下文数量。
- 检索结果做内容去重。
- 如果 embedding 模型加载失败，降级为关键词匹配。
- Chat 和 Diet 共享同一个 retriever，避免重复加载知识库和重复编码。

当前边界：

- 当前代码实际是内存 NumPy 检索，不是 Milvus。
- 当前没有构建标准 RAG 评测集。
- 当前没有严格的 Recall@K、Precision@K、MRR 等离线指标。
- 当前知识库规模较小，更适合 demo 和项目原型，不适合作为完整健身医学知识库宣传。

面试时推荐说法：

> 当前项目已经实现了完整 RAG 链路，但还没有构建标准问答评测集，所以我不会说已经有明确的 Recall@K 数值。当前优化主要集中在 sentence-aware 分块、embedding 检索、阈值过滤、Top-K、去重和 Prompt 约束。后续生产化会补标注评测集，用 Recall@K、Precision@K、MRR 和答案忠实度来系统评估。

### 1.1 建立 RAG 评测集

后续可以构造一批典型健身/营养问题，例如：

- 动作技术类：深蹲、硬拉、卧推、划船、肩推。
- 训练计划类：训练频率、组数次数、恢复周期。
- 营养类：减脂、增肌、蛋白质、碳水、热量缺口。
- 安全边界类：运动损伤、疼痛、特殊人群、医学风险。

每个问题人工标注：

- 应命中的相关 chunk。
- 可接受的参考来源。
- 不应出现的危险建议。
- 标准答案要点。

可用指标：

- `Recall@K`：前 K 个检索结果是否召回相关 chunk，重点衡量“找没找到”。
- `Precision@K`：前 K 个检索结果中相关内容占比，重点衡量“噪声多不多”。
- `MRR`：第一个相关 chunk 的排名，重点衡量“相关内容排得靠不靠前”。
- `Hit Rate@K`：前 K 个结果中是否至少有一个相关 chunk。
- `Answer Faithfulness`：最终回答是否被检索内容支撑，避免模型凭空编造。
- `Citation Accuracy`：回答中的引用是否真实对应检索片段。

### 1.2 调整分块策略

当前使用 sentence-aware 分块，比固定长度切分更不容易截断语义。

后续可以对比：

- `chunk_size=300 / 500 / 800` 的召回效果。
- 是否增加 chunk overlap，例如 50-100 字符。
- 按标题、段落、列表项做结构化分块。
- 对训练动作、营养原则、注意事项分别设计不同分块粒度。

目标：

- 避免 chunk 太短导致上下文不足。
- 避免 chunk 太长导致召回不精准、Prompt 被无关内容占满。
- 让一个 chunk 尽量表达一个完整知识点。

### 1.3 调整 top_k 和 threshold

当前 Chat / Diet 使用：

```text
top_k = 5
threshold = 0.3
```

后续可以基于评测集网格搜索：

```text
top_k: 3 / 5 / 8 / 10
threshold: 0.2 / 0.3 / 0.4 / 0.5
```

观察：

- `top_k` 太小，可能漏召回。
- `top_k` 太大，会引入噪声并增加 Prompt 长度。
- `threshold` 太高，可能无结果。
- `threshold` 太低，可能塞入低相关 chunk。

调参目标不是单纯提高召回，而是在召回率和上下文纯度之间取得平衡。

### 1.4 加入混合检索

当前主要是向量检索，适合语义相似问题。

后续可以加入 BM25 / 关键词检索，形成 hybrid retrieval：

```text
向量召回 top_n
+ BM25/关键词召回 top_n
+ 合并去重
+ 重排
```

适合改善：

- 专业动作名称的精确匹配，例如“罗马尼亚硬拉”“高杠深蹲”。
- 英文缩写或术语，例如 BMI、RPE、HIIT、DOMS。
- 用户 query 很短时的召回不稳定。
- 中文分词不稳定导致的关键词丢失。

### 1.5 加入 reranker

当前是单阶段向量检索：

```text
query embedding -> cosine similarity -> top_k
```

后续可以升级为两阶段：

```text
embedding recall top_20
-> cross-encoder reranker
-> final top_5
```

收益：

- embedding 负责粗召回，保证相关内容先进入候选集。
- reranker 负责精排，提升前几条结果的相关性。
- 对长问题、复杂语义和相似动作区分更友好。

代价：

- 延迟增加。
- 需要额外模型。
- 需要评测集判断收益是否值得。

### 1.6 扩充和治理知识库

当前知识库规模较小，后续可以增加：

- 系统化训练动作库：深蹲、硬拉、卧推、划船、肩推、引体向上等。
- 训练计划设计：频率、容量、强度、周期化、恢复。
- 运动营养：蛋白质、碳水、脂肪、热量、减脂、增肌。
- 常见风险提醒：疼痛、损伤、特殊人群、医学边界。
- 来源元数据：标题、来源、更新时间、主题标签、适用人群。

治理方向：

- 文档去重。
- 过期内容标记。
- 来源可信度分级。
- 不同主题建立标签，方便后续过滤。
- 对医疗/伤病相关内容增加安全提示。

### 1.7 迁移向量数据库

当前内存 NumPy 检索适合小规模 demo。

后续当知识库变大时，可以迁移到 Milvus / FAISS / Qdrant：

- 支持持久化。
- 支持更大规模向量。
- 支持索引，例如 IVF_FLAT / HNSW。
- 支持增量更新。
- 支持元数据过滤。

代码层面已有一定抽象：

- 上层子图只依赖 `retriever.search()`。
- 后续可以替换 retriever 实现，而不需要大改 Chat / Diet 子图。

面试时要注意：

> 当前代码实际是 NumPy 内存检索，Milvus 是生产化迁移方向，不要说成已经完整接入。

### 1.8 加强 Prompt 和答案校验

当前 Prompt 已经要求优先基于参考资料回答，并在资料不足时说明边界。

后续可以增强：

- 强制回答标注引用编号。
- 对没有检索依据的内容做“不确定”表达。
- 增加 answer grounding 检查，判断回答句子是否能被 chunk 支撑。
- 对运动损伤、疾病、药物、极端饮食等高风险话题增加安全模板。
- 输出时区分“知识库依据”和“通用建议”。

## 2. Search 子图优化方向

Search 子图当前流程：

```text
query_understanding -> search -> synthesis
```

当前实现：

- `query_understanding_node` 使用 LLM 将用户问题改写成搜索关键词。
- `search_node` 调用 `TavilySearchTool.search(query, max_results=5)`。
- `synthesis_node` 将搜索结果标题、摘要和 URL 注入 Prompt，让 LLM 生成带来源的回答。
- `TavilySearchTool` 对 query 长度和 `max_results` 做参数校验。
- 没有配置 `TAVILY_API_KEY` 时，会返回 mock 搜索结果，方便测试和演示。
- Tavily 网络错误、鉴权错误和内部错误会被封装为 `ToolResult`，避免异常直接打断子图。

当前边界：

- 当前不是严格 fact-checking 系统。
- 搜索质量依赖 Tavily 返回结果。
- 当前没有对来源域名做可信度分级。
- 当前没有做引用片段级校验。
- 当前没有评估 query rewrite 是否真的提升搜索相关性。
- 当前回答中的来源标注主要依赖 Prompt 约束，不保证每句话都能被来源支撑。

面试时推荐说法：

> Search 子图已经实现了 query rewrite、Tavily 搜索和基于搜索结果的回答合成，但它还不是严格事实校验系统。后续优化重点会放在 query rewrite 评测、来源可信度过滤、引用片段校验、搜索失败降级和回答后验检查上。

### 2.1 Query Rewrite 质量优化

当前 query rewrite 依赖 LLM 把口语化问题改写为 1-2 个搜索关键词。

后续可以优化：

- 构建 query rewrite 测试集，覆盖中文口语、动作名称、营养术语、最新资讯等场景。
- 对比原始 query 和改写 query 的搜索结果相关性。
- 对 query rewrite 增加约束，例如保留核心实体、保留时间范围、避免过度泛化。
- 对短问题或已经很明确的问题跳过 rewrite，减少 LLM 调用和误改写。
- 对需要最新性的 query 自动加入时间词，例如“2026”“latest”“recent”。

可用指标：

- 改写后搜索结果的 `Precision@K`。
- 改写前后首条相关结果排名变化。
- query rewrite 失败率，例如空输出、跑题、丢失核心实体。
- 搜索结果点击/引用命中率。

### 2.2 搜索结果相关性和去噪

当前搜索结果直接进入 synthesis Prompt。

后续可以增加过滤层：

```text
Tavily results
-> domain filter
-> relevance filter
-> dedup
-> rerank
-> synthesis
```

优化方向：

- 去掉标题或摘要为空的结果。
- 对重复 URL、重复标题、重复内容做去重。
- 对明显无关内容做关键词或 embedding 相关性过滤。
- 将 `max_results` 从固定 5 调整为“召回更多、再筛选 top 5”。
- 对搜索结果摘要过短的情况，尝试请求更详细内容或降低回答确定性。

### 2.3 来源可信度过滤

健身和健康问题里，来源质量很重要。

后续可以做来源分级：

- 高可信：WHO、CDC、NIH、NHS、政府/大学/医学机构。
- 中可信：知名健身机构、专业协会、较可靠媒体。
- 低可信：无来源博客、营销页、论坛片段、标题党内容。

可以在 State 中增加来源元数据：

```text
_search_sources = [
  {
    "url": "...",
    "domain": "...",
    "trust_level": "high|medium|low",
    "reason": "WHO domain"
  }
]
```

回答策略：

- 高风险健康问题优先使用高可信来源。
- 来源可信度不足时明确说明“搜索结果不足以支持确定结论”。
- 对营销性质内容降低权重。

### 2.4 Source Grounding 和引用校验

当前 Prompt 要求标注来源，但没有程序化校验。

后续可以增加：

- 回答必须引用 `[来源1]`、`[来源2]`。
- 每个来源编号对应具体 URL。
- 回答生成后检查引用编号是否存在。
- 对关键结论做 evidence check，确认是否能在搜索摘要中找到支撑。
- 若回答包含未被来源支撑的结论，要求模型改写为更保守表达。

目标：

- 降低“看起来有来源，但结论不是来源支持”的风险。
- 防止模型把搜索结果外的信息混进答案。

### 2.5 搜索失败和结果不足时的降级

当前没有 API Key 时会 mock，真实 API 报错时会返回 `ToolResult.fail()`。

后续可以细化降级：

- Tavily 无结果：转为本地 Chat RAG 或给通用建议。
- 搜索结果低相关：明确告诉用户“没有找到足够相关的最新资料”。
- 网络错误：提示搜索服务暂不可用，并降级到本地知识库回答稳定知识。
- 鉴权错误：记录配置问题，不把内部错误暴露给用户。
- 对高风险医疗类 query：不搜索诊断/处方建议，转为安全提醒和就医建议。

### 2.6 搜索子图评测指标

后续可以为 Search 子图建立评测集。

可测问题：

- query rewrite 是否保留核心意图。
- 搜索结果是否相关。
- 回答是否引用真实来源。
- 回答是否忠实于搜索内容。
- 搜索失败时是否有合理 fallback。

可用指标：

- `Query Rewrite Success Rate`：改写结果是否保留核心实体和意图。
- `Search Precision@K`：前 K 条搜索结果相关比例。
- `Source Coverage`：回答中的关键结论有多少能找到来源支撑。
- `Citation Validity`：引用编号是否真实对应来源。
- `Fallback Success Rate`：搜索失败时是否能返回可用、诚实的回答。
- `Latency`：query rewrite、搜索和 synthesis 各阶段耗时。

### 2.7 工程稳定性优化

后续可以补充：

- Tavily Client 复用和超时配置。
- 搜索结果缓存，避免相同 query 短时间重复请求。
- 对搜索 API 失败做重试，但限制重试次数。
- 记录搜索链路日志：原始 query、改写 query、结果数量、是否 mock、耗时。
- 监控 API Key 缺失、网络错误、空结果比例。

## 3. Diet 子图专属优化方向

待补充。

建议后续围绕以下问题记录：

- 用户画像抽取的 JSON 稳定性。
- 身高、体重、性别、目标、偏好的缺失字段处理。
- 热量和宏量营养素估算是否引入确定性计算。
- 特殊人群和疾病边界。
- 个性化推荐的可解释性。

说明：Diet 子图的 RAG 检索优化已放在第 1 节。

## 4. Motion 子图优化方向

Motion 的核心优化方向不是让用户直接准备 `.npz`，而是把当前已实现的“姿态序列分析后半段”扩展为普通用户可使用的图片/视频动作分析。详细需求和技术路线见 [MOTION_MEDIA_PIPELINE_DESIGN.md](../motion/MOTION_MEDIA_PIPELINE_DESIGN.md)，持续维护台账见 [MOTION_OPTIMIZATION_ROADMAP.md](../motion/MOTION_OPTIMIZATION_ROADMAP.md)。

### 4.1 当前定位

已实现：

- Motion 子图：`think -> parse -> tool -> check`。
- `/motion/analyze`：上传 `.npz` 姿态数据。
- `/motion/analyze-image`：上传图片做单帧静态姿态提取和摘要。
- `PoseSequence` 中间格式和 `pose_estimator` 适配器。
- `motion_tool.py`：加载 `(T, J, 3)` 姿态数组，做归一化、FastDTW、余弦相似度、形状差异和整体评价。

未实现：

- 视频上传后的逐帧姿态估计和时序分析。
- 标准动作库数据。
- 动作专项关节角度规则。
- 自训练姿态估计模型。

面试表述应避免把规划说成已落地能力。更准确的说法是：

> 当前 Motion 已经完成姿态序列进入系统后的分析链路，并已支持图片上传后的单帧静态姿态提取。下一步要补齐视频抽帧到 PoseSequence 的时序链路，再复用已有分析算法。

### 4.2 优化顺序

以下是摘要版路线；每一步的当前状态、实际做法和路线偏差以后统一维护在 [MOTION_OPTIMIZATION_ROADMAP.md](../motion/MOTION_OPTIMIZATION_ROADMAP.md)。

1. 定义统一 `PoseSequence` 中间格式。
   - `keypoints: (T, J, C)`。
   - `fps`、`source_type`、`pose_model`、`joint_schema`、`confidence`。
   - `.npz` 作为内部落盘和评测格式，而不是面向普通用户的最终输入。

2. 新增姿态估计适配器。
   - 优先接入 MediaPipe Pose，快速支持图片和短视频关键点提取。
   - 后续可替换为 MoveNet、RTMPose、OpenPose 或 YOLO-Pose。
   - 不从零训练模型，除非后续有标注数据、算力和明确精度目标。

3. 先实现图片分析。
   - 支持 `.jpg`、`.jpeg`、`.png`。
   - 单帧转 `PoseSequence(T=1)`。
   - 输出静态姿态摘要和低置信度提醒。
   - 不承诺动作节奏和完整轨迹。
   - 当前已实现；动作专项关节角度规则放到后续 Step 6。

4. 再实现视频分析。
   - 支持短视频上传。
   - 抽帧、姿态估计、关键点平滑、缺失帧处理。
   - 生成 `PoseSequence(T=N)` 后复用 FastDTW 和多指标相似度。

5. 建设标准动作库。
   - 用标准动作视频通过同一 pose estimator 离线生成 `.npz`。
   - 保证用户动作和标准动作使用一致的关键点 schema。
   - 按深蹲、硬拉、卧推、俯卧撑等高频动作逐步补齐。

6. 建立 Motion 评测集。
   - 姿态估计成功率。
   - 视频关键点连续性。
   - 标准动作对比稳定性。
   - 低质量媒体的拒答/降级准确性。

### 4.3 后续问题清单

建议后续围绕以下问题继续记录：

- 标准动作库 `.npz` 数据补齐。
- 动作类别识别。
- 姿态归一化鲁棒性。
- 关键关节角度指标。
- FastDTW、余弦相似度、shape difference 的阈值标定。
- 基于真实样本的动作评分评测集。
- 与视频姿态提取工具的端到端联调。

## 5. MCP 子图优化方向

当前实现：

- 默认 `MCP_SERVER_COMMAND=mock`，开发、测试和面试演示不依赖本机安装 `howtocook-mcp`。
- 显式配置真实 MCP Server 时，系统会优先尝试真实 subprocess + stdio JSON-RPC 连接。
- 真实 MCP 连接失败时，MCP 子图自动降级到 mock client，并在内部 state 中记录 `_mcp_mode`、`_mcp_configured_command` 和 `_mcp_fallback_reason`，便于调试和面试解释。
- mock 模式仍保留真实 howtocook-mcp 风格的工具名，例如 `mcp_howtocook_getRecipeById`、`mcp_howtocook_whatToEat` 和 `mcp_howtocook_recommendMeals`。

后续建议围绕以下问题记录：

- MCP Client 生命周期管理。
- subprocess 超时和重启。
- tools/list 缓存。
- tools/call 参数校验。
- JSON 解析失败的恢复策略。
- 真实 MCP Server 与 mock 数据的一致性测试。

## 6. Router 和横切能力优化方向

当前 Router 已完成 Phase 3：从关键词 first-match 升级为加权规则、确定性歧义处理、语义样例 fallback 和可选本地 LLM classifier。真实 Qwen provider 已接入并完成 A/B，但因为没有带来准确率收益且平均调用约 6 秒，默认关闭。

工程级 Router 的目标：

- 可解释：每次路由都能说明为什么进入某个子图。
- 可评测：有 router eval 集，能计算 accuracy、precision、recall、fallback rate。
- 可降级：低置信时不要硬分流，可以 fallback 到 chat 或反问澄清。
- 可观测：记录 intent、confidence、reason、scores、source 和耗时。
- 可扩展：后续能从规则路由升级到 semantic router 和 LLM classifier。

推荐实现顺序：

```text
Phase 1: Weighted Rule Router
  -> 保留规则路由，不引入新模型依赖
  -> 从 first-match 改为多 intent 加权打分
  -> 补充口语化触发词
  -> 写入 intent / confidence / reason / scores / source
  -> 低置信 fallback 到 chat
  -> 补 Router 单元测试

Phase 2: Semantic Example Router
  -> 每个 intent 准备典型样例
  -> 规则低置信时用样例相似度分类
  -> 建立 router_eval.jsonl
  -> 当前已落地轻量 char n-gram 相似度版本
  -> 后续可替换为 Sentence-Transformer embedding 相似度

Phase 3: LLM Classifier Fallback
  -> 只在规则和 embedding 都低置信时调用
  -> 要求输出 JSON: intent / confidence / reason / needs_clarification
  -> 解析失败或低置信时 fallback 到 chat 或澄清
  -> 记录 LLM router 的成本、延迟和错误率
  -> 本地 Qwen provider 已接入并完成 A/B，默认关闭

Phase 4: Multi-intent Routing
  -> 支持 primary_intent + secondary_intents
  -> 支持组合子图，例如 search -> diet
  -> 处理“我想减脂，帮我查最新饮食研究”这类多意图问题
```

### 6.1 Phase 1: Weighted Rule Router

本阶段先落地，不引入额外模型或外部服务。

当前 first-match 逻辑：

```text
按 KEYWORD_MAP 顺序扫描
命中第一个关键词就返回 intent
没有命中则 chat
```

优化后：

```text
扫描所有规则
对每个 intent 累加分数
选择最高分 intent
根据最高分和分差计算 confidence
低置信 fallback 到 chat
把路由原因和 scores 写入 RouterState
```

建议新增状态字段：

```text
_route_scores: dict[str, float]
_route_confidence: float
_route_reason: str
_route_source: "weighted_rules" | "semantic_examples" | "llm_classifier" | "fallback"
_route_matches: list[str]
```

第一版重点覆盖这些误分场景：

- “我最近想瘦一点，有什么建议？”应进入 `diet`，不能因为“最近”误进 `search`。
- “最近有什么健身新闻？”应进入 `search`。
- “帮我看看深蹲哪里不对”应进入 `motion`。
- “番茄炒蛋步骤是什么？”应进入 `mcp`。
- “蛋白质有什么作用？”更偏知识解释，建议进入 `chat`。

### 6.2 Phase 2: Semantic Example Router

当规则低置信时，使用语义样例路由处理更隐式的口语表达。

当前已落地轻量版本：

- 新增 `SEMANTIC_EXAMPLES`，为 `search`、`motion`、`diet`、`mcp`、`chat` 配置典型样例。
- 规则分数不足或规则置信度较低时，调用样例相似度路由。
- 当前使用 char n-gram Jaccard 相似度，不新增模型下载和运行时依赖。
- 命中时 `_route_source = "semantic_examples"`。
- 新增 `data/eval/router_eval.jsonl` 作为 Router 评测样例集，当前覆盖 66 条样本。
- `tests/test_router.py` 会读取该评测集，验证当前 Router 输出符合预期。
- 新增 `scripts/eval_router.py`，输出 accuracy、per-intent precision/recall/F1、evaluation slices、confusion matrix、route source counts 和 mismatches。
- 新增样本按主流 intent routing 评测切片组织：`implicit_intent`、`low_confidence`、`fallback_unclear`、`freshness_search`、`multi_intent_primary`、`boundary_concept`、`boundary_training_plan`、`recipe_tool`、`tool_file_signal`。
- 当前单 intent Router 的 primary intent policy 是：显式搜索/最新研究优先 `search`，动作文件或姿势判断优先 `motion`，具体做菜优先 `mcp`，个性化饮食规划优先 `diet`，泛化训练建议或不清楚时 `chat`。
- `data/eval/router_challenge_eval.jsonl` 已从 20 条扩充到 36 条。经过确定性边界修正后当前为 36/36；它仍作为困难边界基线，不应把小样本满分解释成生产泛化完成。
- Challenge set 已补充 `primary_intent`、`secondary_intents`、`route_plan` 和 `expected_failure_reason`，用于提前定义多意图场景下的主意图、次意图、未来组合执行顺序和当前失败原因。

评测命令：

```bash
python scripts/eval_router.py --fail-on-mismatch
python scripts/eval_router.py --json
python scripts/eval_router.py --dataset data/eval/router_challenge_eval.jsonl
```

当前评测集覆盖：

- Chat vs Diet：蛋白质概念解释、蛋白质摄入规划、隐式体型改善。
- Chat vs Motion：深蹲好处、深蹲疼痛、卧推/硬拉姿势。
- Search vs Diet：显式搜索研究、最近想控制体重。
- MCP vs Motion：做菜“怎么做”和动作“怎么做”的区分。
- Fallback：问候和泛化训练建议。

样例：

```text
diet:
  - 我最近想瘦一点
  - 我想控制体重
  - 我想吃得健康一点

motion:
  - 帮我看看深蹲哪里不对
  - 我的硬拉姿势有问题吗

search:
  - 查一下最新健身研究
  - 最近有什么训练新闻
```

用户 query 和样例做相似度匹配，按 intent 聚合分数。后续如果环境允许，可以把当前 char n-gram 相似度替换为 Sentence-Transformer embedding 相似度，并缓存样例向量。

### 6.3 Phase 3: LLM Classifier Fallback

只在规则和语义样例都不确定时调用 LLM，降低成本和不稳定性。

当前已落地工程契约和真实本地 Qwen provider，但 provider 默认关闭：

- `_build_llm_router_prompt()` 生成严格 JSON 输出提示词。
- `_call_llm_router()` 复用进程级共享 `LLMLoader`；通过 `LLM_ROUTER_ENABLED=1` 显式开启。
- `_extract_json_object()` 只接受可解析的 JSON object。
- `_llm_classifier_route()` 只接受合法 intent、非澄清请求、且 `confidence >= 0.70` 的结果。
- JSON 解析失败、intent 非法、低置信、需要澄清、provider 未配置时，都不会硬分流到业务子图，而是回退到 `chat` 或最终 fallback。
- Ambiguity detector 会记录全部 signals，但只有少数 review signals 会调用 LLM，避免高频模型分类。
- 高置信规则场景中，LLM 置信度必须高于规则置信度才能覆盖。
- A/B 中绿色集保持 66/66，challenge 保持 36/36；但 5 次调用平均约 6.22 秒且仅 1 次接管，因此默认关闭真实 LLM。

期望输出：

```json
{
  "intent": "diet",
  "confidence": 0.78,
  "reason": "用户表达了体重管理和饮食建议需求",
  "needs_clarification": false
}
```

低置信或解析失败时，不硬分流。

本次实际执行顺序：

1. 先在评测集中增加更多低置信、隐式表达和多意图样本。
2. 接入真实 LLM provider，但只在规则与语义样例都无法高置信判断时触发。
3. 记录 LLM 路由的命中率、解析失败率、低置信率、平均延迟和成本。
4. 对比“无 LLM fallback”和“有 LLM fallback”的 eval accuracy、fallback rate 与误路由率。
5. A/B 结果显示没有净收益且延迟明显，因此真实 provider 默认关闭。

#### Phase 3 优先验证样本：`蛋炒饭怎么做`

`蛋炒饭怎么做` 是一个适合加入 Router challenge/eval 的典型样本。它的问题不是缺少某个菜名关键词，而是“怎么做”同时适用于菜谱、训练动作和计划建议。

建议将这一类样本拆成一组边界用例：

```text
蛋炒饭怎么做 -> mcp
水煮鱼怎么做 -> mcp
深蹲怎么做 -> motion
硬拉怎么做比较安全 -> motion
减脂餐怎么做 -> challenge，可能需要区分 Diet 与 MCP
高蛋白早餐怎么安排 -> diet 或 challenge，取决于是否要求具体菜谱
```

实际实施策略：

1. 新增 ambiguity detector，只记录“X 怎么做 / 做法 / 步骤 / 教程”这类高歧义句式，不直接硬路由。
2. 对高置信规则仍直接返回，例如 `.npz`、上传动作、显式搜索、明确菜谱。
3. 对歧义样本先走 semantic examples；如果仍低置信，再触发 LLM classifier fallback。
4. LLM classifier 只输出 JSON，不生成回答，字段沿用当前契约：`intent`、`confidence`、`reason`、`needs_clarification`。
5. 对 `needs_clarification=true` 或低置信样本，优先 fallback 到 Chat 或生成澄清问题，不硬分流。
6. 用绿色回归集防止已有行为退化，用 challenge set 观察“蛋炒饭怎么做”这类歧义样本是否被修正。

#### Phase 3 要解决的核心问题

Phase 1 和 Phase 2 已经把“高置信显式信号”和“低置信口语表达”覆盖到了一个可解释、可评测的水平，但 challenge set 里仍然有一类问题很难只靠规则或少量语义样例稳定处理：

- 高歧义句式：例如 `X 怎么做`、`怎么安排`、`先讲原理再看动作`。
- 多信号竞争：同一句里同时出现动作词、菜谱词、饮食目标或最新研究信号。
- 顺序约束：例如 `先分析动作，再查最新纠正方法`。
- 否定约束：例如 `不需要具体做法`，应该压制 `mcp` 信号。

所以 Phase 3 不是“把 Router 交给 LLM 重做一遍”，而是只在前两层都不够确定时，让 LLM 作为一个受约束的裁判，专门处理这些歧义边界。

#### Phase 3 的边界

这一阶段故意不做下面几件事：

- 不让 LLM 直接生成最终回答，只做 intent classification。
- 不替换高置信规则路由，规则命中时仍然直接走确定性路径。
- 不跳过 `semantic examples`，而是把 LLM 放在它后面作为最后一道低频 fallback。
- 不在 Phase 3 里引入多子图串联执行；multi-intent route plan 仍属于 Phase 4。

这样做的原因是：当前项目的主要价值在于可解释和可评测，Phase 3 需要先证明“有限引入 LLM”比“全量交给 LLM”更稳，而不是为了炫复杂度破坏现有确定性行为。

#### Phase 3 的实际落地顺序

本次已按下面顺序完成：

1. 先扩充 challenge/eval 样本，重点覆盖高歧义句式、否定约束、顺序词和多信号竞争。
2. 保持当前 `_build_llm_router_prompt()`、`_call_llm_router()`、`_llm_classifier_route()` 这套契约不变，用 mock/provider hook 验证 acceptance rule。
3. 新增 ambiguity detector 或低置信触发条件，只把真正需要二次判断的样本送到 LLM classifier。
4. 接入真实 LLM provider，但只允许它输出严格 JSON，不生成自然语言答案。
5. 记录触发率、有效命中率、低置信率、解析失败率、平均延迟和额外成本。
6. 用相同 challenge set 对比“无 LLM fallback”和“有 LLM fallback”的收益，再决定是否保留。

#### Phase 3 的验收口径

Phase 3 是否值得保留，不看“看起来更智能”，而看下面几项是否真的改善：

- 绿色回归集不能退化，`router_eval.jsonl` 仍应保持稳定高准确率。
- challenge set 中与歧义句式相关的样本应有可量化提升。
- `llm_classifier` 的触发率应保持低频，说明它真的是 fallback 而不是主路由。
- JSON 解析失败、非法 intent、低置信回退都必须可观测。
- 平均延迟和成本要在可接受范围内，否则收益不值得。

当前 A/B 没有显示准确率收益，平均延迟约 6 秒，因此采用上述降级结论：默认保持确定性 Router，真实 LLM 仅作为关闭状态的实验能力保留。

#### Phase 3 和 Phase 4 的关系

Phase 3 关注的是“单 intent 下的歧义裁决”，Phase 4 关注的是“一个请求里识别并记录多个 intent，再决定是否串联多个子图”。两者相关，但不要混在一起：

- `蛋炒饭怎么做` 这类问题，优先属于 Phase 3 的歧义分类问题。
- `先分析深蹲动作，再查最新纠正方法` 这类问题，最终会延伸到 Phase 4 的 multi-intent route plan。
- Phase 3 可以先帮助我们更稳定地选出 `primary_intent`，为 Phase 4 打基础。

#### 面试表达建议

可以这样讲：

> Router Phase 3 已经完成真实本地 Qwen A/B，不是停留在设计层。确定性 Router 在绿色集和 36 条 challenge 上都是 100%；开启 Qwen 后没有提高准确率，5 次调用只接管 1 次，平均约 6.22 秒，并且在没有置信度保护时出现过误覆盖。因此我默认关闭真实 LLM，只保留严格契约、feature flag、ambiguity signals 和观测指标。这个结论来自评测，而不是主观选择。

### 6.4 Phase 4: Multi-intent Routing

详细设计见 [MULTI_INTENT_ROUTING_DESIGN.md](../router/MULTI_INTENT_ROUTING_DESIGN.md)。

后续支持多意图：

```json
{
  "primary_intent": "search",
  "secondary_intents": ["diet"],
  "route_plan": ["search", "diet"]
}
```

适合处理：

```text
我想减脂，帮我查一下最近有什么有效饮食方法
```

当前项目已完成 Phase 4 的受控多意图路由：保留单 intent 兼容语义，只对白名单中的四种两步组合执行多子图，并统一合成结果。任意组合和三步计划仍作为后续生产化方向。

推荐落地顺序：

1. 先识别和记录 `primary_intent`、`secondary_intents`、`route_plan`，但仍只执行 `primary_intent` 对应子图。
2. 用 challenge set 评估多意图识别是否改善。
3. 只对少数高价值组合支持串联执行，例如 `search -> diet`、`motion -> chat`。
4. 最后再考虑组合结果合成和流式输出。
