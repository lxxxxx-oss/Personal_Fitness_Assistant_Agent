# 健身智能助手 Agent 项目文档

## 1. 项目是做什么的

健身智能助手 Agent 是一个基于 LangGraph 的多任务 LLM Agent 系统。它不是简单的聊天机器人，而是把用户问题先做意图路由，再分发给不同专业子图处理。

系统目前覆盖 5 类能力：

| 能力 | 说明 |
|---|---|
| 健身知识问答 | 基于本地知识库做 RAG 检索，再由 LLM 生成回答 |
| 联网搜索 | 对需要实时信息的问题调用 Tavily 搜索，返回带来源的回答 |
| 饮食推荐 | 提取用户身高、体重、目标、偏好，结合营养知识生成建议 |
| 3D 动作分析 | 加载 `.npz` 姿态数据，做姿态归一化、FastDTW 对齐和相似度分析 |
| 菜谱工具调用 | 自实现 MCP Client，对接 howtocook-mcp 或 mock 菜谱工具 |

整体架构：

```text
用户输入
  -> Router：加权规则意图分类
      -> Chat 子图：RAG 健身知识问答
      -> Search 子图：Query 改写 -> Tavily 搜索 -> 回答合成
      -> Diet 子图：画像提取 -> 营养知识检索 -> 饮食建议
      -> Motion 子图：think -> parse -> tool -> check
      -> MCP 子图：工具发现 -> 工具选择 -> 工具调用 -> 结果格式化
  -> 返回回答
```

## 2. 技术栈

| 层级 | 技术 |
|---|---|
| 后端框架 | FastAPI、Pydantic、uvicorn |
| 图编排 | LangGraph、StateGraph、条件边、子图嵌套 |
| LLM | Qwen3-0.6B，HuggingFace Transformers 本地加载 |
| 向量检索 | Sentence-Transformers + NumPy 余弦相似度，后续可迁移 Milvus |
| 姿态算法 | NumPy、SciPy、FastDTW、Pillow；MediaPipe 为图片姿态估计可选依赖 |
| 工具协议 | 自实现 subprocess + stdio JSON-RPC 2.0 MCP Client |
| 搜索 | Tavily API，带 mock 降级 |
| 前端 | Web UI、微信小程序原生 WXML/WXSS/JS |
| 部署 | Docker、docker-compose |
| 测试 | pytest，测试中 mock LLM、embedding、搜索和 MCP 外部依赖 |

## 3. 当前进度

| 模块 | 当前状态 |
|---|---|
| 顶层 Router | Phase 4 已完成：保留 Phase 3 的 hybrid classifier，并新增多意图观测、四种白名单两步组合、子图错误隔离和最终结果合成；真实 Qwen classifier 仍因收益不足默认关闭 |
| Chat RAG | 已完成，支持共享知识库检索和记忆注入 |
| Search 搜索 | 已完成，支持 Tavily 和 mock 降级 |
| Diet 饮食推荐 | 已完成，画像提取 + 营养 RAG + 个性化建议 |
| Motion 动作分析 | 子图、算法、`PoseSequence` 中间格式、姿态估计适配器、`.npz` 分析接口和图片静态姿态接口已完成；缺标准动作库数据，视频上传接口仍待补 |
| MCP 菜谱工具 | 已完成 MCP Client，默认 mock 模式；显式配置真实 server 时会优先连接真实 MCP，失败后自动降级到 mock |
| 滑动窗口记忆 | 已完成，默认保留 6 轮对话，按 `user_id` 隔离 |
| SSE 流式 | 已完成，`POST /chat/stream` |
| WebSocket 流式 | 已完成，`/chat/ws` |
| Web UI | 已完成，通过 `/ui` 访问；已支持 Motion 图片上传入口，并在请求处理期间显示明确状态提示 |
| 微信小程序 | 代码完成，待端到端联调 |
| Docker | 文件已写，待完整构建验证 |
| `/motion/analyze` | 已实现基础 `.npz` 上传分析；支持 `PoseSequence` metadata schema；传入 `reference_name` 时可对比标准动作库 |
| `/motion/analyze-image` | 已实现图片上传后的单帧静态姿态提取和摘要；不能判断完整动作节奏、轨迹或发力顺序 |
| Milvus | 文档规划过，当前代码仍是内存 NumPy 检索 |

当前测试结果：`114 passed, 1 skipped, 1 warning`。warning 来自 Starlette TestClient/httpx 兼容层弃用提示，不影响运行行为。

## 4. 关键目录

```text
app/
├── main.py                 # FastAPI 入口
├── config.py               # 配置
├── graph/
│   ├── router.py           # 顶层路由图
│   ├── state.py            # RouterState
│   └── subgraphs/          # chat/search/diet/motion/mcp 子图
├── tools/                  # retriever/search/motion/mcp 工具
├── memory/                 # 滑动窗口记忆
├── llm/                    # LLM 加载器
└── static/                 # Web UI

data/
└── knowledge/              # 健身、营养、WHO/CDC 知识库

miniprogram/                # 微信小程序端

tests/                      # 单元测试、集成测试、手工测试脚本

docs/
├── README.md               # 当前文档
└── API.md                  # API 详细说明
```

## 5. 已遇到的问题和处理方式

| 问题 | 处理方式 | 当前状态 |
|---|---|---|
| LLM 容易把确定性任务做错 | 意图分类优先使用加权规则和语义样例；LLM classifier 只作为低置信 fallback 契约，工具参数解析尽量用确定性逻辑 | 已落地 |
| LangGraph 图执行和 token 流式输出职责冲突 | 子图先构建 `_prompt`，流式层再单独调用 `generate_stream()` | 已落地 |
| Sentence-Transformer 首次下载依赖网络 | 检索器加载失败时降级为关键词匹配 | 已落地 |
| Tavily API Key 缺失会影响搜索 | SearchTool 支持 mock 搜索结果 | 已落地 |
| MCP Server 未安装时不可用 | `MCP_SERVER_COMMAND` 默认 `mock`；显式配置真实 MCP Server 时，连接失败会自动降级到 mock 菜谱数据，并记录 fallback 原因 | 已落地 |
| Web UI 提问后空白等待，用户不知道系统状态 | 发送消息后立即显示“正在分析/调用工具”状态；收到 intent meta 后更新状态；请求失败时给出明确错误说明 | 已落地 |
| 本地 LLM 被多个子图节点重复加载，可能导致系统内存耗尽 | `LLMLoader` 使用进程级共享模型缓存；并发首次加载加锁；共享模型生成串行化；SSE/WebSocket 不再先生成完整答案再重复流式生成 | 已落地 |
| 3D 动作分析缺少标准动作库和视频输入适配 | 无 `.npz` 时返回动作分析说明和数据准备方法，不瞎猜用户动作问题；图片已可转 PoseSequence 做静态摘要，视频仍需补抽帧和时序分析 | `.npz` 和图片静态分析已落地，视频和标准库仍待补 |
| 小程序使用 SSE 有兼容性差异 | 使用 `wx.request enableChunked`，低版本可降级到非流式 `/chat` | 已写代码，待联调 |
| Docker 中模型路径跨平台 | `config.py` 已支持 `MODEL_PATH` 等环境变量；compose 仍需按机器调整模型挂载路径 | 已部分处理 |
| 本机测试命令不可用 | 已安装测试所需核心依赖并复现测试；当前为 `94 passed, 1 skipped, 1 warning` | 已处理 |

## 6. 后端接口

详细参数见 [API.md](./API.md)。

当前代码中的接口：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| POST | `/chat` | 非流式对话 |
| POST | `/chat/stream` | SSE 流式对话 |
| WebSocket | `/chat/ws` | WebSocket 流式对话 |
| GET | `/chat/{user_id}/history` | 获取会话历史 |
| DELETE | `/chat/{user_id}/history` | 清空会话历史 |
| GET | `/ui` | Web UI |
| POST | `/motion/analyze` | 上传 `.npz` 做动作基础分析，可选标准动作对比 |
| POST | `/motion/analyze-image` | 上传图片做单帧静态姿态提取和摘要 |

## 7. 运维和开发命令

以下命令默认在项目根目录执行：

```powershell
cd C:\Users\黎\Desktop\Personal_Fitness_Assistant_Agent-master
```

### 7.1 两台电脑协作流程

两台电脑统一使用 `main` 分支。每次开始工作前，先在当前电脑同步远端最新代码：

```bash
git checkout master
git status
git pull origin master
```

如果 `git status` 显示有未提交修改，先确认这些修改是否需要保留，再选择提交或暂存，不要直接覆盖。每次阶段性工作结束后，再提交并推送：

```bash
git status
git add .
git commit -m "描述本次修改"
git push origin master
```

另一台电脑测试前只需要进入自己的项目目录，然后执行：

```bash
git checkout master
git pull origin master
```

这样可以避免 `main` / `master` 分支混用，也能减少两台电脑之间出现 unrelated histories 或本地文件覆盖冲突的概率。

### 7.2 安装依赖

```bash
pip install -r requirements.txt
```

如果需要体验 Motion 图片静态姿态分析，即 `/motion/analyze-image` 或 Web UI 的图片上传入口，需要安装额外依赖：

```bash
pip install -r requirements-motion.txt
```

说明：

- `requirements.txt` 是基础后端、RAG、Router、MCP、`.npz` Motion 分析和测试依赖。
- `requirements-motion.txt` 额外安装 `mediapipe`，用于真实图片关键点提取。
- 建议使用 Python 3.11 的 conda 或 venv 环境安装 Motion 依赖，减少 MediaPipe wheel 兼容问题。

### 7.3 启动后端

Conda 环境推荐启动链路：

```powershell
cd D:\Users\Agent\Personal_Fitness_Assistant_Agent
conda activate fitness-agent
pip install -r requirements.txt
$env:MCP_SERVER_COMMAND="mock"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

本地模型运行约束：

- 使用本地 Qwen 模型时保持单进程单 worker，不要增加 `--workers`。
- 多 worker 会让每个进程各自加载一份模型，重新引入数 GB 级内存复制。
- 同一 worker 内的 Chat、Diet、Search、Motion、MCP 和流式接口会共享一份 tokenizer/model。
- 并发生成会在共享模型层串行执行，优先保证内存稳定；需要高并发时应改为独立模型服务，而不是增加 uvicorn worker。

如需同时体验 Motion 图片上传分析，先补充安装和模型文件：

```powershell
pip install -r requirements-motion.txt
New-Item -ItemType Directory -Force data\models
curl.exe -L -o data\models\pose_landmarker.task https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task
```

然后重启后端，打开 `http://127.0.0.1:8000/ui` 上传图片验证。

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Windows 桌面环境下也可以使用项目脚本启动：

```powershell
.\scripts\run_backend.cmd
```

该脚本会设置 `MCP_SERVER_COMMAND=mock`，并将后端日志写入：

```text
logs/uvicorn.out.log
logs/uvicorn.err.log
```

局域网或小程序联调时：

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 7.4 健康检查

```bash
curl http://127.0.0.1:8000/health
```

预期返回：

```json
{"status":"ok","version":"0.1.0"}
```

### 7.4 打开 Web UI

```text
http://127.0.0.1:8000/ui
```

### 7.5 非流式对话测试

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"u1\",\"message\":\"如何做一个标准深蹲？\"}"
```

### 7.6 SSE 流式对话测试

```bash
curl -N -X POST http://127.0.0.1:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"u1\",\"message\":\"减脂期间吃什么？\"}"
```

### 7.7 查看和清空历史

```bash
curl http://127.0.0.1:8000/chat/u1/history
```

```bash
curl -X DELETE http://127.0.0.1:8000/chat/u1/history
```

### 7.8 运行测试

```bash
python -m pytest tests/ -q
```

如果报 `No module named pytest`：

```bash
pip install pytest pytest-asyncio
python -m pytest tests/ -q
```

### 7.9 Router Eval

```bash
python scripts/eval_router.py --fail-on-mismatch
```

The script reads `data/eval/router_eval.jsonl` and reports accuracy, per-intent precision/recall/F1, evaluation slices, a confusion matrix, route source counts, and mismatches.

Current router eval set: 66 cases, 100.0% accuracy. The expanded set includes mainstream routing slices such as implicit intent, low-confidence/fallback, freshness search, multi-intent primary routing, recipe-tool routing, training-plan boundaries, and file/tool signals.

Challenge eval for known hard/failing cases:

```bash
python scripts/eval_router.py --dataset data/eval/router_challenge_eval.jsonl
```

Current challenge set: 36 cases. Primary intent, secondary intent exact match, and route-plan exact match are all 36/36. The local Qwen classifier remains disabled by default because the earlier A/B preserved accuracy but added about 6.22 seconds per reviewed case. Phase 4 executes only `search -> diet`、`search -> chat`、`motion -> chat`、`motion -> diet`; unsupported combinations remain observable but safely fall back to the primary route.

Multi-intent routing design: [technical/router/MULTI_INTENT_ROUTING_DESIGN.md](./technical/router/MULTI_INTENT_ROUTING_DESIGN.md).

Phase 3 roadmap for router ambiguity handling: [technical/interview-archive/SUBGRAPH_OPTIMIZATION_GUIDE.md](./technical/interview-archive/SUBGRAPH_OPTIMIZATION_GUIDE.md#63-phase-3-llm-classifier-fallback).

Detailed test record: [tests/2026-06-25-router-eval-and-challenge-test.md](./tests/2026-06-25-router-eval-and-challenge-test.md).

For machine-readable output:

```bash
python scripts/eval_router.py --json
```

### 7.10 Docker

```bash
docker compose up --build
```

注意：

- `docker-compose.yml` 当前挂载了 Windows 本地模型路径。
- 如果换机器，需要修改模型挂载路径。
- `app/config.py` 已支持 `MODEL_PATH`、`MODEL_DEVICE` 等环境变量覆盖。

### 7.11 微信小程序联调

1. 启动后端：

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

2. 微信开发者工具导入 `miniprogram/`。
3. 使用测试 AppID。
4. 开发阶段勾选“不校验合法域名”。
5. 确认小程序 API 地址指向本机或局域网 IP。
6. 依次测试：
   - 启动健康检查。
   - 普通知识问答。
   - 饮食推荐。
   - 联网搜索或 mock 搜索。
   - 菜谱 MCP 或 mock。
   - 历史记录加载和清空。
   - 流式打字机效果。

生产环境要求：

- 后端必须使用 HTTPS/WSS。
- 微信后台需要配置 request 合法域名。

## 8. 配置说明

主要配置在 `app/config.py`：

| 配置 | 说明 |
|---|---|
| `model_path` | Qwen3 模型路径 |
| `model_device` | `cpu` 或 `cuda` |
| `model_max_tokens` | 最大生成 token |
| `llm_router_enabled` | 是否启用本地 Qwen Router A/B，默认 `false` |
| `llm_router_max_tokens` | Router classifier 最大输出 token，默认 128 |
| `embedding_model` | Sentence-Transformer 模型名 |
| `tavily_api_key` | Tavily API Key，默认读取环境变量 |
| `motion_library_dir` | 标准动作库目录 |
| `react_max_iterations` | Motion ReAct 最大迭代次数 |
| `mcp_server_command` | MCP Server 命令，默认 `mock`；可通过 `MCP_SERVER_COMMAND=howtocook-mcp` 切换真实 server，失败会降级到 mock |
| `api_host` / `api_port` | 后端服务地址和端口 |

已支持环境变量覆盖：

- `MODEL_PATH`
- `MODEL_DEVICE`
- `MODEL_MAX_TOKENS`
- `MODEL_TEMPERATURE`
- `MODEL_TOP_P`
- `LLM_ROUTER_ENABLED`
- `LLM_ROUTER_MAX_TOKENS`
- `MEMORY_MAX_TURNS`
- `RETRIEVER_TOP_K`
- `RETRIEVER_THRESHOLD`
- `EMBEDDING_MODEL`
- `MOTION_LIBRARY_DIR`
- `REACT_MAX_ITERATIONS`
- `MCP_SERVER_COMMAND`
- `API_HOST`
- `API_PORT`
- `MEDIAPIPE_POSE_MODEL_PATH`

这些配置支持 Docker 和本地部署按环境覆盖。

Motion 图片姿态估计说明：

- `mediapipe` 0.10+ 使用 Tasks API 时需要本地 `pose_landmarker.task` 模型文件。
- 默认查找路径为 `data/models/pose_landmarker.task`。
- 也可以通过 `MEDIAPIPE_POSE_MODEL_PATH` 指向绝对路径。
- 如果未配置模型文件，`/motion/analyze-image` 会返回 503，并提示模型缺失。
- 模型文件属于本地运行资产，当前 `.gitignore` 会忽略 `data/models/` 和 `*.task`，两台电脑需要分别准备。

## 9. 下一步优先级

1. 按 [Motion 优化路线](./technical/motion/MOTION_OPTIMIZATION_ROADMAP.md) 继续实现视频抽帧到 `PoseSequence` 的动作序列分析入口。
2. 准备 `data/motions/` 标准动作库。
3. 完成微信小程序端到端联调。
4. 验证 Docker 构建和启动。
5. 根据需要迁移 Milvus。
6. 完善 MCP 超时、进程生命周期和错误处理。
7. Router Phase 4 已完成；后续先积累真实多意图样本和组合成功率，再决定是否扩充白名单或支持三步计划，不直接开放任意子图组合。

## 10. 保留文档说明

当前 docs 顶层只保留：

- `README.md`：项目说明、进度、问题处理、运维方式。
- `API.md`：接口细节。
- `DOCUMENTATION_MAP.md`：文档脉络、阅读顺序和维护边界。

历史阶段记录仍保留在子目录：

- `interview/`：面向面试准备的分级背诵材料，只保留可直接学习和回答面试的问题。
- `technical/`：技术设计、路线图、历史长文档和专题状态记录，不作为直接背诵入口。
- `progress/`：阶段开发记录；日常先看 [progress/README.md](./progress/README.md)，单篇日期记录作为证据保留。
- `tests/`：手工测试记录和体验测试语句；日常先看 [tests/README.md](./tests/README.md)，单篇测试记录作为证据保留。
- `miniprogram/`：小程序设计和实施记录。
- `superpowers/`：早期设计方案和计划。

## 11. Codex 配置说明

本项目最初包含 Claude 专用配置，现已迁移为 Codex 可用的项目配置：

```text
AGENTS.md
.codex/
├── README.md
├── COMMANDS.md
└── skills/
    ├── auto-document/
    │   └── SKILL.md
    └── check-tool-spec/
        └── SKILL.md
```

迁移逻辑：

- 原 Claude 自动文档维护规则迁移为 `.codex/skills/auto-document/SKILL.md`。
- 原 Claude 工具规范检查规则迁移为 `.codex/skills/check-tool-spec/SKILL.md`。
- 原 Claude 命令权限白名单迁移为 `.codex/COMMANDS.md` 的命令参考。
- Codex 实际协作入口为根目录 `AGENTS.md`。

## 12. 文档维护约定

后续修改代码时，需要同步检查并维护文档，避免代码和说明脱节。

补充约定：

> 后续新增后端用户可见能力时，也要同步检查 Web UI 是否需要入口或状态展示；不能只实现 API 而让 `/ui` 无法体验。

简要维护规则：

| 修改内容 | 需要同步检查 |
|---|---|
| 后端接口、请求/响应字段、SSE 或 WebSocket 协议 | `docs/API.md` |
| 项目能力、模块进度、已知问题、处理方式、运行命令、部署方式 | `docs/README.md` |
| 微信小程序页面、组件、API 封装、联调方式 | `docs/miniprogram/` |
| 面试讲解材料、项目答辩稿、针对项目的问答库 | `docs/interview/` |
| 技术设计、路线图、历史长文档、专题状态记录 | `docs/technical/` 或 `docs/progress/` |
| 阶段性实现、重构、问题修复过程 | `docs/progress/`，并同步 `docs/progress/README.md` |
| 手工测试、冒烟测试、分级验收 | `docs/tests/`，并同步 `docs/tests/README.md` |
| 早期方案、规格设计 | `docs/superpowers/`，一般只保留或归档，不随意删除 |

判断标准：

> 如果一次代码修改会改变“项目是做什么的、目前进度、如何运行、接口如何调用、遇到的问题、问题如何处理”中的任意一项，就必须同步更新对应文档。

完整准则见 [DOCUMENTATION_MAP.md](./DOCUMENTATION_MAP.md#5-文档维护准则)。
