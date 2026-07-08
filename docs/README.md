# 健身智能助手 Agent 项目文档

本文档是项目当前状态的事实入口：回答项目做什么、已经做到哪里、当前边界和下一步。运行命令集中在 [RUNBOOK.md](./RUNBOOK.md)，接口细节集中在 [API.md](./API.md)。

## 1. 项目定位

健身智能助手是一个基于 LangGraph 的多任务 LLM Agent 原型。系统先判断用户意图，再把请求交给对应专业子图，不是把所有能力塞进一个通用 Prompt。

产品层聚焦四类核心能力；代码层为了隔离营养建议与外部菜谱工具，保留五条执行路径：

| 能力 | 当前做法 |
|---|---|
| 健身知识问答 | 本地知识库 RAG 检索后由 LLM 生成回答 |
| 联网搜索 | Tavily 搜索、来源整理和 mock 降级 |
| 饮食与菜谱建议 | Diet 负责用户画像、营养检索和饮食建议；MCPTool 负责外部菜谱工具发现与调用 |
| 动作分析 | 图片/视频转 PoseSequence，视频可选择同 schema 标准动作执行 FastDTW 与多指标相似度分析 |

项目展示重点是：四类业务任务的受控编排、可评测 Router、Motion 数值算法、MCP 标准化工具调用、Milvus RAG/Search 数据增强，以及记忆、流式输出和失败降级。

## 2. 系统架构

```text
用户输入
  -> Router：hybrid classifier + 多意图观测
      -> Chat：RAG 健身知识问答
      -> Search：Query 改写 -> Tavily/mock -> 回答合成
      -> Diet：画像提取 -> 营养 RAG -> 饮食/菜谱建议
      -> Motion：think -> parse -> tool -> check
      -> MCP：工具发现 -> 调用规划 -> JSON-RPC 工具调用 -> 结果格式化
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
| Chat RAG | 已完成 Milvus/内存可配置 Retriever、共享知识库检索和记忆注入；真实服务效果基线待补 |
| Search | 已完成 Tavily 接入和 mock 降级 |
| Diet | 已完成画像提取、营养 RAG 和建议生成 |
| Motion | 图片/视频 PoseSequence、标准视频构建脚本、schema 安全比较及小程序参考选择已完成；平滑、周期切分、正式标准样本集和专项规则待补 |
| MCP | Client、initialize 握手、`tools/list`、`tools/call`、content 解析和 MCP 子图已完成；默认 mock，真实 Server 需显式配置与联调 |
| Memory | 已完成滑动窗口记忆，默认保留 6 轮并按 `user_id` 隔离 |
| 流式接口 | SSE 和 WebSocket 已完成；WebSocket 通过线程到 asyncio queue 桥接实现真实逐 token 发送 |
| Web UI | `/ui` 可用，支持对话状态提示和 Motion 图片上传 |
| 微信小程序 | Chat 主链路、执行模式展示及 Motion 图片/视频上传闭环已完成；开发者工具和真机联调未完成 |
| Docker | 配置文件已提供，完整构建验证未完成 |

当前文档记录的自动化测试结果为 `139 passed, 2 skipped, 1 warning`。warning 来自 Starlette TestClient/httpx 兼容层弃用提示，不影响当前行为。专项验收入口见 [tests/README.md](./tests/README.md)。

## 4. 已知边界与工程取舍

| 边界或问题 | 当前处理 | 生产化方向 |
|---|---|---|
| LLM 不适合完全承担确定性路由 | 加权规则、语义样例和离线 eval 优先；LLM classifier 默认关闭 | 积累真实困难样本后再评估接管收益 |
| 本地 LLM 重复加载可能 OOM | 进程级模型缓存、首次加载锁和生成串行化 | 拆成独立模型推理服务 |
| Embedding 首次加载依赖网络 | 加载失败时降级为关键词匹配 | 固化模型资产并建设向量服务 |
| Tavily 未配置或调用失败 | 未配置 key 时返回 mock；真实调用失败时返回可处理错误并记录降级 warning | 增加超时、重试、熔断和可观测性 |
| mock/fallback 容易被误认为真实执行 | 三种对话协议统一返回 `execution`，小程序用绿色/黄色标签展示真实与降级模式 | 增加依赖级健康检查和请求追踪 |
| MCP 与 Diet 同属饮食域 | 对外都服务饮食场景，内部按“营养生成”和“外部工具调用”隔离 | 产品入口可统一，MCP 保留为通用工具适配层 |
| Milvus 真实效果尚缺基线 | Retriever、Schema、索引、幂等写入和容器配置已完成 | 补真实冒烟、Recall@K、MRR 与 P95 延迟基线 |
| Motion 缺正式标准样本集 | 已提供标准视频构建脚本和同 schema 相似度链路；legacy 17 点占位数据会被拒绝 | 采集同视角标准动作、教练标注、周期切分和专项规则 |
| 图片只包含单帧信息 | 只输出姿态提取和静态摘要 | 视频输入转换为 `PoseSequence` 后分析完整动作 |
| 小程序 WebSocket 存在端侧与网络差异 | 建连或执行失败时降级到非流式接口 | 完成真机、弱网和不同基础库版本验收 |
| Docker 模型路径跨机器 | 配置支持环境变量覆盖 | 使用平台无关镜像和模型服务 |

## 5. 对外接口

详细请求字段、响应结构、状态码和示例见 [API.md](./API.md)。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
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

- 健康检查：`http://127.0.0.1:8000/health`
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

1. 为 RAG 建立标准问答与检索评测集，补 Recall@K、MRR 和来源覆盖率。
2. 按 [Motion 优化路线](./technical/motion/MOTION_OPTIMIZATION_ROADMAP.md) 补关键点平滑、动作周期切分、正式标准样本集和专项纠错规则。
3. 完成真实 MCP Server 的稳定性、超时、Schema、进程生命周期和权限联调。
4. 补全 Search 的逐条 citation 与正文引用关系校验。
5. 完成 Milvus 真实服务冒烟，并建立检索质量与延迟基线。
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
