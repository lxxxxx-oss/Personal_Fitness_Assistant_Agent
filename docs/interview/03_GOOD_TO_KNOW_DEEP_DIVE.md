# P2 了解即可：深挖兜底材料

这份不用逐字背，目标是在面试官继续追问时有话可说。

## 1. 关键调用链

普通聊天请求：

```text
FastAPI /chat
  -> 构造 RouterState
  -> LangGraph 顶层 Router
  -> intent_classify_node
  -> 对应子图
  -> finalize_node
  -> 返回 result / error
```

流式请求：

```text
FastAPI /chat/stream
  -> Router 判断路径
  -> 子图准备上下文
  -> 最终生成阶段逐步输出 token
  -> 前端 SSE 展示
```

图片动作分析：

```text
Web UI 上传图片
  -> /motion/analyze-image
  -> 姿态估计适配器
  -> PoseSequence
  -> Motion 分析结果
  -> 前端展示摘要和建议
```

## 2. Router 四阶段

### Phase 1：Weighted Rule Router

解决问题：避免 first-match 导致一个关键词抢走全部路由。

讲法：

> 我把规则改成加权打分，每个 intent 都可以累积分数，最后选最高分，并记录命中原因。

### Phase 2：Semantic Example Router

解决问题：用户表达不一定包含关键词。

讲法：

> 对一些低置信样本，用轻量语义样例做补充。当前不是完整 embedding router，而是工程上轻量可控的相似度方案。

### Phase 3：LLM Classifier Fallback

解决问题：规则和语义样例都不确定时，需要一个可选裁判。

讲法：

> 我真实接入过本地 Qwen 做 A/B，但它没有提高准确率，还带来约 6 秒平均延迟，因此默认关闭。这个结论说明我不是迷信 LLM，而是用评测决定是否启用。

### Phase 4：Multi-intent Routing

解决问题：真实用户会一句话提出多个任务。

讲法：

> Phase 4 增加 primary intent、secondary intents 和 route plan。执行层只开放四种两步白名单组合，其他组合降级为主意图单路由，最后用 final synthesis 合成结果。

## 3. Motion 深挖口径

### Q：为什么普通用户不会上传 `.npz`，这个设计还合理？

回答：

> `.npz` 不是给普通用户直接上传的终态产品格式，而是系统内部的统一姿态序列格式。用户上传图片或视频，系统用姿态估计模型提取关键点，再转成统一格式给动作分析模块。这样上层输入可以变化，下层动作分析逻辑保持稳定。

### Q：为什么不自己训练姿态估计模型？

回答：

> 个人项目从零训练姿态估计模型成本很高，也不是这个 Agent 项目的核心。更合理的工程路线是接入 MediaPipe、MoveNet、OpenPose 这类开源模型，把重点放在 Agent 如何使用模型输出、如何做动作规则分析、如何把结果解释给用户。

### Q：关键点怎么变成动作是否标准？

回答：

> 关键点本身只是坐标。要判断动作质量，需要计算关节角度、身体对齐关系、轨迹变化、动作阶段和与标准动作序列的相似度。比如深蹲可以看膝髋角度、膝盖是否内扣、躯干前倾、最低点深度和上升下降节奏。

当前边界：

- 图片只能做静态姿态分析。
- 视频才能更好判断轨迹和节奏。
- 真实专业化需要标准动作库和动作专项规则。

## 4. RAG 深挖口径

如果问“召回率是多少”：

> 当前项目重点是原型链路，暂时没有大规模标注集来给出生产级 recall。我的优化路线是先构建问题到证据片段的评测集，再统计 recall@k、MRR 和无关片段比例。现在不能编一个虚假的指标，但可以说明如何评测和优化。

如果问“怎么优化 RAG”：

> 第一是知识库治理，保证来源可靠；第二是 chunk 策略，避免切碎语义；第三是调整 top_k 和 threshold；第四是混合检索结合关键词和向量；第五是加 reranker；第六是建立检索和回答两层评测。

## 5. 生产化升级路线

可以按模块讲：

- Router：接入线上日志，统计真实路由准确率、澄清率、多意图组合成功率。
- RAG：迁移 Milvus / pgvector，补充 reranker、引用校验和 RAG eval。
- Motion：接入视频分析、标准动作库、动作专项规则和真实用户样本。
- MCP：增加工具权限、超时、重试、熔断和审计日志。
- Memory：从内存 session 迁移到 Redis / PostgreSQL。
- 部署：容器化、健康检查、日志监控、配置隔离。

## 6. 白板题模板

### 架构图

```text
User / Web UI / MiniProgram
  -> FastAPI
  -> LangGraph Router
       -> Chat RAG
       -> Search
       -> Diet RAG
       -> Motion Tool
       -> MCP Tools
  -> Streaming / JSON Response
```

### RAG 流程

```text
Question
  -> Query preprocess
  -> Retrieve chunks
  -> Build grounded prompt
  -> LLM answer
  -> Answer with boundary
```

### Motion 流程

```text
Image / Video
  -> Pose Estimator
  -> Keypoints
  -> PoseSequence
  -> Angle / similarity / rule analysis
  -> Coaching feedback
```

## 7. 面试最后一分钟总结

可以这样收尾：

> 这个项目我最想展示的不是某一个模型效果，而是 AI Agent 应用开发里的工程思路：如何把 LLM、RAG、工具、动作分析和外部协议放进一个可控工作流；如何用 Router eval 证明改动没有破坏主流程；如何诚实地区分原型能力和生产化路线。它现在是一个可运行的面试型原型，核心链路能演示，边界也清楚，后续可以沿着数据、评测和部署继续增强。

## 8. 可以反问面试官

- 如果团队做 Agent，更看重开放式自主规划，还是受控工作流的稳定性？
- 你们评估 Agent 项目时，更关注任务完成率、工具调用成功率，还是端到端用户满意度？
- 在业务里接入 LLM Router 时，你们通常如何平衡准确率、延迟和可解释性？
