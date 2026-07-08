# 运行与联调手册

本文档集中维护本地开发、测试、评测、Docker 和端侧联调命令。项目能力和当前进度看 [README.md](./README.md)，接口参数看 [API.md](./API.md)。

MCP 是简历和面试材料中的工具协议亮点。默认 `MCP_SERVER_COMMAND=mock` 用于离线测试和稳定演示；显式配置真实 Server 命令时，系统会走 subprocess + stdio JSON-RPC，并在连接失败时记录原因后回退 mock。

以下命令默认在项目根目录执行。Windows 示例目录为：

```powershell
cd D:\Users\Agent\Personal_Fitness_Assistant_Agent
```

## 1. 快速启动

推荐使用 Python 3.11 的 `fitness-agent` Conda 环境：

```powershell
conda activate fitness-agent
pip install -r requirements.txt
$env:MCP_SERVER_COMMAND="mock"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

本地模型运行时保持单进程、单 worker。多个 worker 会分别加载模型，可能重新引入数 GB 内存复制；同一 worker 内的子图共享 tokenizer/model，并发生成在共享模型层串行执行。

Windows 桌面环境也可以使用项目脚本：

```powershell
.\scripts\run_backend.cmd
```

脚本默认使用 mock MCP，日志写入：

```text
logs/uvicorn.out.log
logs/uvicorn.err.log
```

## 2. 安装依赖

基础后端、RAG、Router、MCP、`.npz` Motion 分析和测试：

```powershell
pip install -r requirements.txt
```

体验 `/motion/analyze-image`、`/motion/analyze-video` 或 Web UI 图片上传时，还要安装 MediaPipe 与 OpenCV：

```powershell
pip install -r requirements-motion.txt
New-Item -ItemType Directory -Force data\models
curl.exe -L -o data\models\pose_landmarker.task https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task
```

说明：

- 建议在 Python 3.11 的 Conda 或 venv 环境安装 Motion 依赖。
- 默认模型路径为 `data/models/pose_landmarker.task`。
- 可通过 `MEDIAPIPE_POSE_MODEL_PATH` 覆盖模型路径。
- `data/models/` 和 `*.task` 被 `.gitignore` 忽略，两台电脑需要分别准备。
- 缺少模型文件时，图片和视频姿态接口返回 503 和明确的缺失提示。

用标准动作视频构建与当前 MediaPipe 视频链路同 schema 的参考 PoseSequence：

```powershell
python scripts/build_motion_reference.py .\standard_squat.mp4 `
  --name squat_standard `
  --library-dir data\motions
```

脚本默认拒绝覆盖同名参考；确认替换时显式增加 `--overwrite`。参考名称只允许字母、数字、下划线和连字符。标准视频与用户视频必须使用同一姿态模型和 `joint_schema`，否则接口返回 422，不会强行计算无意义分数。

查看参考库兼容状态并执行视频对比：

```powershell
curl.exe http://127.0.0.1:8000/motion/references
curl.exe -X POST http://127.0.0.1:8000/motion/analyze-video `
  -F "file=@user_squat.mp4" `
  -F "reference_name=squat_standard"
```

## 3. 服务检查

健康检查：

```powershell
curl.exe http://127.0.0.1:8000/health
```

预期返回：

```json
{"status":"ok","version":"0.1.0"}
```

Web UI：

```text
http://127.0.0.1:8000/ui
```

非流式对话：

```powershell
curl.exe -X POST http://127.0.0.1:8000/chat `
  -H "Content-Type: application/json" `
  -d '{"user_id":"u1","message":"如何做一个标准深蹲？"}'
```

SSE 流式对话：

```powershell
curl.exe -N -X POST http://127.0.0.1:8000/chat/stream `
  -H "Content-Type: application/json" `
  -d '{"user_id":"u1","message":"减脂期间吃什么？"}'
```

查看和清空历史：

```powershell
curl.exe http://127.0.0.1:8000/chat/u1/history
curl.exe -X DELETE http://127.0.0.1:8000/chat/u1/history
```

更完整的请求示例和上传接口说明见 [API.md](./API.md)。

## 4. 测试与 Router Eval

运行自动化测试：

```powershell
python -m pytest tests/ -q
```

如果缺少 pytest：

```powershell
pip install pytest pytest-asyncio
python -m pytest tests/ -q
```

Router 绿色回归集：

```powershell
python scripts/eval_router.py --fail-on-mismatch
```

Router challenge set：

```powershell
python scripts/eval_router.py --dataset data/eval/router_challenge_eval.jsonl
```

机器可读输出：

```powershell
python scripts/eval_router.py --json
```

当前绿色回归集为 66 条、100% accuracy；challenge set 为 36 条，primary intent、secondary intent 和 route plan exact match 均为 36/36。详细结果和边界以 [tests/README.md](./tests/README.md) 为入口。

## 5. 两台电脑协作

项目当前统一使用 `master` 分支。每次开始工作前：

```powershell
git switch master
git status
git pull origin master
```

如果有未提交修改，先确认是否需要保留，不要直接覆盖。阶段性工作结束后：

```powershell
git status
git add .
git commit -m "描述本次修改"
git push origin master
```

另一台电脑测试前执行：

```powershell
git switch master
git pull origin master
```

## 6. 局域网与微信小程序联调

后端监听局域网地址：

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

联调步骤：

1. 微信开发者工具导入 `miniprogram/`。
2. 使用测试 AppID。
3. 开发阶段勾选“不校验合法域名”。
4. 确认小程序 API 地址指向本机局域网 IP。
5. 依次验证健康检查、普通问答、饮食推荐、搜索、MCP、历史记录和流式效果。

生产环境需要 HTTPS/WSS，并在微信后台配置 request 合法域名。当前小程序代码基本完成，但端到端联调仍未完成。

## 7. Docker

```powershell
docker compose up --build
```

当前边界：

- `docker-compose.yml` 挂载了 Windows 本地模型路径，换机器时需要调整。
- `app/config.py` 支持 `MODEL_PATH`、`MODEL_DEVICE` 等环境变量覆盖。
- Docker 文件已经提供，但完整构建和启动仍待验证。

## 8. 配置速查

主要配置位于 `app/config.py`：

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
| `mcp_server_command` | MCP Server 命令，默认 `mock`；真实 server 失败后降级到 mock |
| `api_host` / `api_port` | 后端服务地址和端口 |

支持的主要环境变量：

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

## 9. 常见运行边界

- Sentence-Transformer 首次加载可能需要联网；失败时检索器降级为关键词匹配。
- Tavily API Key 缺失时 SearchTool 使用 mock 搜索结果。
- `MCP_SERVER_COMMAND` 默认为 `mock`；显式使用真实 MCP Server 时，连接失败会自动降级。
- Motion 图片入口只做单帧静态姿态摘要，不能判断完整节奏、轨迹或发力顺序。
- 本地模型适合单机演示；高并发生产环境应拆成独立模型服务。
