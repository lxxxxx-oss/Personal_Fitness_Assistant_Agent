# 健身智能助手 Agent 项目文档

本文档是项目当前状态的事实入口：回答项目做什么、已经做到哪里、当前边界和下一步。运行命令集中在 [RUNBOOK.md](./RUNBOOK.md)，接口细节集中在 [API.md](./API.md)。

## 1. 项目定位

健身智能助手是一个基于 LangGraph 的多任务 LLM Agent 原型。系统先判断用户意图，再把请求交给对应专业子图，不是把所有能力塞进一个通用 Prompt。

产品层聚焦四类核心能力；当前面试口径统一为：Chat/Diet 融合进 Knowledge 能力域，MCP 是工具协议补充，Motion 按完整标准动作教练系统表达，Milvus RAG 已完成真实链路效果评测。

| 能力 | 当前做法 |
|---|---|
| 健身知识问答 | Knowledge 能力域统一承接 Chat/Diet，本地知识库 RAG 检索后由 LLM 生成回答 |
| 联网搜索 | Tavily 搜索、来源整理和 mock 降级 |
| 饮食与菜谱建议 | Diet 作为 Knowledge 内部链路负责用户画像、营养检索和饮食建议；MCPTool 只是外部菜谱/工具协议补充 |
| 动作分析 | 完整标准动作教练系统：图片/视频转 PoseSequence，选择同 schema 标准动作执行 FastDTW 与多指标相似度分析，并输出教练式动作反馈 |

项目展示重点是：四类业务任务的受控编排、可评测 Router、Motion 数值算法、MCP 标准化工具调用、Milvus RAG/Search 数据增强，以及记忆、流式输出和失败降级。

## 2. 系统架构

```text
用户输入
  -> Router：hybrid classifier + 多意图观测
      -> Knowledge：Chat/Diet 融合问答
      -> Search：Query 改写 -> Tavily/mock -> 回答合成
      -> Knowledge diet_advice：画像提取 -> 营养 RAG -> 饮食建议
      -> Motion：标准动作教练系统
      -> MCP：工具协议补充 -> JSON-RPC 工具调用 -> 结果格式化
  -> 白名单组合执行或单路由执行
  -> 返回回答
```

主要技术栈：

| 层级 | 技术 |
|---|---|
| 后端 | FastAPI、Pydantic、uvicorn |
| 图编排 | LangGraph、StateGraph、条件边、子图嵌套 |
| LLM | Qwen3-0.6B、HuggingFace Transformers 本地加载 |
| 检索 | Sentence-Transformers + Milvus IVF_FLAT/COSINE；支持幂等 upsert、来源字段与内存降级 |
| 姿态算法 | NumPy、SciPy、FastDTW、Pillow、OpenCV；MediaPipe 为图片/视频姿态估计可选依赖 |
| 工具协议 | subprocess + stdio JSON-RPC 2.0 MCP Client，支持真实 Server 与 mock fallback |
| 前端 | Web UI、微信小程序原生 WXML/WXSS/JS |
| 测试 | pytest、Router 离线评测、专项验收记录 |

## 3. 当前实现状态

| 模块 | 当前状态 |
|---|---|
| Router | Phase 4 已完成：保留 Phase 3 hybrid classifier，增加多意图观测、四种白名单两步组合、错误隔离和结果合成；真实 Qwen classifier 因收益不足默认关闭 |
| Knowledge RAG | Chat/Diet 已融合为 Knowledge 能力域；已完成 Milvus/内存可配置 Retriever、编号证据块、知识来源标识透传、记忆注入和真实链路效果评测；Chat 与 Diet 的 RAG 检索已通过 `ToolRegistry` 的 `knowledge.retrieve` 执行 |
| Search | 已完成 Tavily 接入、mock 降级，并作为第一个真实子图接入最小 `ToolRegistry`，通过 `search.tavily` 统一执行搜索工具 |
| Knowledge-Diet | 作为 Knowledge 内部 `diet_advice` 链路，已完成 Pydantic 结构化画像解析、身高体重范围/枚举校验、非法输出 warning 降级、营养 RAG 和建议生成 |
| Motion | 已按完整标准动作教练系统口径完成图片/视频输入、PoseSequence、标准视频构建脚本、schema 安全比较、小程序参考选择、相似度计算和教练式反馈 |
| Tool System | 已落地最小 `ToolRegistry` 原型：`ToolSpec` 记录 name、description、input_schema、permission、executor、timeout、retry、fallback；Registry 支持注册、列出、schema 校验、权限检查、执行、有限重试、fallback、`execution_id`、`duration_ms` 和 audit log；Search、Knowledge/RAG 与 MCP execute 已接入 Registry，Motion 仍由 LangGraph/API 直接控制工具调用 |
| MCP | 定位为工具协议补充；轻量 Client 已实现 subprocess/stdio、initialize、`tools/list`、`tools/call` 和首个 text content block 解析；`execute_tool_node` 已通过 `ToolRegistry` 调用 `mcp.call_tool`，默认 mock 用于演示稳定 |
| Memory | 会话缓冲区按 `user_id` 隔离并最多保存 6 轮；当前由 Knowledge 能力域消费最近 6 条消息（约 3 轮），用于普通问答和饮食建议的连续上下文；跨 Search、Motion、MCP 的长期记忆消费仍是后续增强项 |
| 异步接口 | HTTP/SSE/WebSocket 的同步 LangGraph 阶段通过 `asyncio.to_thread` 执行；SSE 与 WebSocket 共用线程到 asyncio queue 桥接逐 token 输出，避免阻塞事件循环；模型生成锁仍保证同进程串行推理 |
| Web UI | `/ui` 可用，支持对话状态提示和 Motion 图片上传 |
| 微信小程序 | Chat 主链路、执行模式展示及 Motion 图片/视频上传闭环已完成；开发者工具和真机联调未完成 |
| Docker | 配置文件已提供，完整构建验证未完成 |

当前文档记录的自动化测试结果为 `172 passed, 2 skipped, 1 warning`。默认 pytest 通过 fixture 替换本地 LLM 生成和 SentenceTransformer 编码，主要证明接口、状态流、工具治理、算法与降级契约可回归；两个 skip 分别是本地真实模型和需显式 `MILVUS_TEST_URI` 的真实 Milvus 测试。真实 Qwen Router A/B、MediaPipe 媒体冒烟另有专项记录。warning 来自 Starlette TestClient/httpx 兼容层弃用提示。验收入口见 [tests/README.md](./tests/README.md)。

## 4. 已知边界与工程取舍

| 边界或问题 | 当前处理 | 生产化方向 |
|---|---|---|
| LLM 不适合完全承担确定性路由 | 加权规则、语义样例和离线 eval 优先；LLM classifier 默认关闭 | 积累真实困难样本后再评估接管收益 |
| 本地 LLM 重复加载可能 OOM | 进程级模型缓存、首次加载锁和生成串行化 | 拆成独立模型推理服务 |
| Embedding 首次加载依赖网络 | 加载失败时降级为关键词匹配 | 固化模型资产并建设向量服务 |
| Tavily 未配置或调用失败 | 未配置 key 时返回 mock；真实调用失败时返回可处理错误并记录降级 warning | 增加超时、重试、熔断和可观测性 |
| Diet 画像来自 LLM | JSON 解析后通过 Pydantic 校验；非法、越界或非对象输出降级为空画像并产生 warning | 增加多轮补全、用户确认和敏感画像治理 |
| mock/fallback 容易被误认为真实执行 | 三种对话协议统一返回 `execution`，小程序用绿色/黄色标签展示真实与降级模式 | 增加依赖级健康检查和请求追踪 |
| Chat/Diet 容易被问是否重复 | 统一解释为 Knowledge 能力域：对外保留兼容意图，对内按 `general_qa` 和 `diet_advice` 分链路 | 后续继续沉淀结构化用户画像和更细粒度 Answer Benchmark |
| 工具系统容易被问是否只是函数调用 | 已补最小 `ToolSpec + ToolRegistry` 原型，统一管理 schema、权限、超时字段、有限重试、fallback、`execution_id`、`duration_ms` 和审计；Search、Knowledge/RAG 与 MCP execute 已接入；Motion compare 是下一步候选 | 评估 Motion 标准动作比较是否接入 Registry，媒体上传和姿态估计继续保留 API 边界 |
| MCP 与 Diet 同属饮食域 | MCP 明确定位为工具协议补充，不是饮食主链路；Diet/Knowledge 负责营养建议，MCP 负责外部工具适配；MCP execute 已进入 Registry 工具治理 | 补真实 Server 的发现结果 allowlist、inputSchema 深校验、响应 ID、进程生命周期和安全隔离 |
| Milvus 效果评测 | 已完成真实链路效果评测，证明 Collection、写入、检索、source 透传和 API 主链路可用 | 扩大 Recall@K、MRR、生成忠实度与 P95 延迟基线规模 |
| Motion 标准动作教练系统 | 已形成图片/视频 -> PoseSequence -> 标准动作对比 -> 教练式反馈闭环 | 扩充正式标准样本集、周期切分、专项规则和教练标注 |
| 图片只包含单帧信息 | 只输出姿态提取和静态摘要 | 视频输入转换为 `PoseSequence` 后分析完整动作 |
| 小程序 WebSocket 存在端侧与网络差异 | 建连或执行失败时降级到非流式接口 | 完成真机、弱网和不同基础库版本验收 |
| Docker 模型路径跨机器 | 配置支持环境变量覆盖 | 使用平台无关镜像和模型服务 |
| 服务没有认证与限流 | 当前只绑定本机地址用于开发演示；`user_id` 不是身份凭证 | 接入认证授权、用户级访问控制、限流和审计 |
| 会话仅在进程内 | `_sessions` 按用户键保存，重启丢失且没有用户键淘汰 | 使用带 TTL 的 Redis/数据库，并提供删除与隐私治理 |
| CORS 与错误边界偏宽 | CORS 允许任意来源，部分内部异常可能进入 500 detail | 配置来源白名单、统一安全错误响应和日志脱敏 |
| `/health` 只证明进程存活 | 固定返回版本，不探测模型、检索或外部工具 | 拆分 liveness 与 readiness，并展示依赖级状态 |

### 本地原型安全声明

当前 API 没有登录鉴权、租户隔离或请求限流，`user_id` 只是客户端提供的会话键。知道某个 `user_id` 的调用方可以读取或清空对应内存历史；CORS 也允许任意浏览器来源。项目默认监听 `127.0.0.1`，只适合本地开发和面试演示，不应直接暴露到公网。生产化前必须补认证授权、HTTPS、来源白名单、会话 TTL/持久化、上传与请求限流、错误脱敏和审计日志。

## 5. 对外接口

详细请求字段、响应结构、状态码和示例见 [API.md](./API.md)。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 进程存活检查，不检查外部依赖 readiness |
| POST | `/chat` | 非流式对话 |
| POST | `/chat/stream` | SSE 流式对话 |
| WebSocket | `/chat/ws` | WebSocket 流式对话 |
| GET | `/chat/{user_id}/history` | 获取会话历史 |
| DELETE | `/chat/{user_id}/history` | 清空会话历史 |
| GET | `/ui` | Web UI |
| POST | `/motion/analyze` | 上传 `.npz`，可选标准动作对比 |
| POST | `/motion/analyze-image` | 上传图片并生成单帧静态姿态摘要 |
| POST | `/motion/analyze-video` | 上传短视频并生成多帧姿态序列摘要 |
| GET | `/motion/references` | 查看标准动作及视频比较兼容状态 |

## 6. 快速运行

```powershell
conda activate fitness-agent
pip install -r requirements.txt
$env:MCP_SERVER_COMMAND="mock"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

启动后访问：

- 进程存活检查：`http://127.0.0.1:8000/health`
- Web UI：`http://127.0.0.1:8000/ui`

Motion 图片/视频分析需要额外安装 `requirements-motion.txt` 并准备 `data/models/pose_landmarker.task`。完整安装、配置、测试、Router eval、Docker 和小程序联调命令见 [RUNBOOK.md](./RUNBOOK.md)。

## 7. 关键目录

```text
app/                         后端、LangGraph、工具、记忆和 Web UI
data/knowledge/              本地健身与营养知识库
data/eval/                   Router 绿色回归集和 challenge set
data/motions/                标准动作库预留目录
miniprogram/                 微信小程序端
tests/                       自动化测试源码
docs/interview/              P0/P1/P2 面试复习材料
docs/technical/              技术设计、专题状态和历史长文档
docs/progress/               阶段性实现与修复证据
docs/tests/                  测试执行和手工验收记录
docs/superpowers/            早期方案与规格
```

## 8. 下一步优先级

1. 扩充 RAG 标准问答与检索评测集，扩大 Recall@K、MRR 和来源覆盖率样本规模。
2. 按 [Motion 优化路线](./technical/motion/MOTION_OPTIMIZATION_ROADMAP.md) 扩充标准动作样本库、关键点平滑、动作周期切分和专项纠错规则。
3. 按 [Motion/MCP Registry 迁移评估](./technical/tool-registry/MOTION_MCP_REGISTRY_MIGRATION_EVALUATION.md) 评估 Motion 标准动作比较是否接入 `ToolRegistry`，媒体上传和姿态估计继续保留 API 边界。
4. 补全 Search 的逐条 citation 与正文引用关系校验。
5. 在已完成 Milvus 真实链路效果评测基础上，扩大检索质量与延迟基线。
6. 完成微信小程序端到端联调和 Docker 跨机器构建验证。
7. 积累真实多意图样本与组合成功率，再决定是否扩充 Router 白名单。

## 9. 文档入口

| 想了解什么 | 阅读入口 |
|---|---|
| 项目当前状态 | 本文档 |
| 接口协议 | [API.md](./API.md) |
| 运行和联调 | [RUNBOOK.md](./RUNBOOK.md) |
| 面试复习 | [interview/README.md](./interview/README.md) |
| 技术设计 | [technical/README.md](./technical/README.md) |
| 开发过程 | [progress/README.md](./progress/README.md) |
| 验收证据 | [tests/README.md](./tests/README.md) |
| 完整文档分流规则 | [DOCUMENTATION_MAP.md](./DOCUMENTATION_MAP.md) |

当前事实以 `README.md` 和 `API.md` 为准；历史计划和 progress 记录不能覆盖已经更新的当前状态。
