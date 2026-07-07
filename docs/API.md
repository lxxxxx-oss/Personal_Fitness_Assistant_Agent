# 健身智能助手 API 文档

Base URL：

```text
http://127.0.0.1:8000
```

当前后端入口：`app/main.py`

## 1. 接口总览

| 方法 | 路径 | 说明 | 状态 |
|---|---|---|---|
| GET | `/health` | 健康检查 | 已实现 |
| POST | `/chat` | 非流式对话 | 已实现 |
| POST | `/chat/stream` | SSE 流式对话 | 已实现 |
| WebSocket | `/chat/ws` | WebSocket 流式对话 | 已实现 |
| GET | `/chat/{user_id}/history` | 获取对话历史 | 已实现 |
| DELETE | `/chat/{user_id}/history` | 清空对话历史 | 已实现 |
| GET | `/ui` | Web UI 静态页面 | 已实现 |
| POST | `/motion/analyze` | 上传 `.npz` 做独立动作分析，可选标准动作对比 | 已实现 |
| POST | `/motion/analyze-image` | 上传图片做单帧静态姿态提取和摘要 | 已实现 |
| POST | `/motion/analyze-video` | 上传短视频并生成多帧姿态序列摘要 | 已实现 |

## 2. 健康检查

```http
GET /health
```

响应：

```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

命令：

```bash
curl http://127.0.0.1:8000/health
```

## 3. 非流式对话

```http
POST /chat
Content-Type: application/json
```

请求体：

```json
{
  "user_id": "u1",
  "message": "如何做一个标准深蹲？"
}
```

字段说明：

| 字段 | 类型 | 必填 | 限制 |
|---|---|---|---|
| `user_id` | string | 是 | 1-64 字符 |
| `message` | string | 是 | 1-4096 字符 |

响应：

```json
{
  "user_id": "u1",
  "intent": "motion",
  "reply": "...",
  "sources": [],
  "warnings": [],
  "execution": [
    {"component": "motion", "mode": "guidance_only", "degraded": true, "detail": "No uploaded pose data was available"},
    {"component": "llm", "mode": "local_qwen", "degraded": false, "detail": ""}
  ]
}
```

`sources` 返回执行链路收集并去重后的来源 URL，主要由 Search 子图产生；没有外部来源时为空列表。`warnings` 返回组合执行、工具调用或降级过程中产生的非致命提示。`execution` 公开本次请求实际使用的依赖与模式，客户端据此区分真实执行和 mock/fallback；该字段不会包含 Token、服务命令、文件路径或原始异常。逐条 citation 与正文引用关系校验仍是后续项。

`execution` 元素结构：

| 字段 | 类型 | 说明 |
|---|---|---|
| `component` | string | `llm`、`rag`、`search`、`mcp` 或 `motion` |
| `mode` | string | 实际模式，例如 `local_qwen`、`milvus`、`memory_fallback`、`tavily`、`mock` |
| `degraded` | boolean | 是否使用 mock、fallback 或低能力降级路径 |
| `detail` | string | 对外安全的简短原因，无补充时为空字符串 |

命令：

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"u1\",\"message\":\"如何做一个标准深蹲？\"}"
```

## 4. SSE 流式对话

```http
POST /chat/stream
Content-Type: application/json
Accept: text/event-stream
```

请求体与 `/chat` 相同。

事件流示例：

```text
event: meta
data: {"intent":"diet","sources":[],"warnings":[],"execution":[{"component":"rag","mode":"milvus","degraded":false,"detail":""},{"component":"llm","mode":"local_qwen","degraded":false,"detail":""}]}

data: 减脂

data: 期间

event: done
data: {}
```

事件说明：

| 事件 | 说明 |
|---|---|
| `meta` | 首个事件，返回 intent、sources、warnings 和 execution 执行轨迹 |
| 默认 `data` | LLM token 文本 |
| `done` | 生成结束 |

命令：

```bash
curl -N -X POST http://127.0.0.1:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"u1\",\"message\":\"减脂期间吃什么？\"}"
```

## 5. WebSocket 流式对话

```text
ws://127.0.0.1:8000/chat/ws
```

客户端发送：

```json
{
  "user_id": "u1",
  "message": "怎么做番茄炒蛋？"
}
```

服务端返回：

```json
{"type":"meta","intent":"mcp","sources":[],"warnings":[],"execution":[{"component":"mcp","mode":"mock","degraded":true,"detail":"MCP demo mode configured"},{"component":"llm","mode":"local_qwen","degraded":false,"detail":""}]}
{"type":"token","text":"番茄炒蛋"}
{"type":"token","text":"..."}
{"type":"done"}
```

错误返回：

```json
{"type":"error","message":"Missing user_id or message"}
```

说明：

- WebSocket 接口适合微信小程序或需要双向连接的客户端。
- 当前实现为一次连接处理一条用户消息，发送完成后服务端关闭连接。

## 6. 获取对话历史

```http
GET /chat/{user_id}/history
```

响应：

```json
{
  "user_id": "u1",
  "history": [
    {"role": "user", "content": "what is a squat?"},
    {"role": "assistant", "content": "..."}
  ]
}
```

命令：

```bash
curl http://127.0.0.1:8000/chat/u1/history
```

说明：

- 历史按 `user_id` 隔离。
- 默认保留最近 6 轮对话。

## 7. 清空对话历史

```http
DELETE /chat/{user_id}/history
```

响应：

```json
{
  "user_id": "u1",
  "status": "cleared"
}
```

命令：

```bash
curl -X DELETE http://127.0.0.1:8000/chat/u1/history
```

## 8. Web UI

```text
http://127.0.0.1:8000/ui
```

说明：

- 静态文件来自 `app/static/`。
- 后端启动后可直接用浏览器访问。

## 9. 动作上传分析

当前对外开放的动作分析接口包括三个入口：

- `/motion/analyze`：上传 `.npz` 姿态序列，支持可选标准动作库对比。
- `/motion/analyze-image`：上传图片，提取单帧人体姿态并返回静态姿态摘要。
- `/motion/analyze-video`：上传短视频，受控抽帧并生成多帧 `PoseSequence` 摘要。

注意：图片接口只能分析单帧静态姿态；视频接口当前只验证视频到姿态序列，不包含动作周期切分、关键点平滑、标准动作评分或专项纠错。

```http
POST /motion/analyze
Content-Type: multipart/form-data
```

请求字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | file | 是 | `.npz` 姿态数据文件，推荐使用 `keypoints` 数组，形状为 `T x J x C`；当前分析层使用前三维坐标 |
| `reference_name` | string | 否 | 标准动作库中的动作名称，对应 `data/motions/{reference_name}.npz` |

不传 `reference_name` 时，接口只校验和加载上传的姿态数据，返回帧数、关键点数量等基础信息。

传入 `reference_name` 时，接口会从 `config.motion_library_dir` 中查找同名标准动作，并返回 DTW 距离、余弦相似度、形状差异和整体评价。

`.npz` 姿态数据说明：

- 推荐 key：`keypoints`。
- 兼容旧 key：`pose`、`positions`。
- 推荐 shape：`T x J x C`。
- 当前 Motion 分析层要求至少前三维坐标，并会使用前三维作为 `x/y/z`。
- 可选 metadata：`fps`、`source_type`、`pose_model`、`joint_schema`、`confidence`、`meta_*`。
- `.npz` 是内部持久化、调试、评测和标准动作库格式，不是后续图片/视频用户输入的最终形态。

响应示例：

```json
{
  "filename": "sample.npz",
  "frames": 8,
  "joints": 17,
  "reference": null,
  "metrics": null,
  "message": "姿态数据已加载。未提供 reference_name，当前仅返回基础信息；如需标准动作对比，请在 data/motions/ 中准备同名 .npz 并传入 reference_name。"
}
```

命令：

```bash
curl -X POST http://127.0.0.1:8000/motion/analyze \
  -F "file=@sample.npz"
```

带标准动作对比：

```bash
curl -X POST http://127.0.0.1:8000/motion/analyze \
  -F "file=@sample.npz" \
  -F "reference_name=squat"
```

错误：

| 状态码 | 场景 |
|---|---|
| 422 | 上传文件不是 `.npz`，或 `.npz` 内部数组格式不合法 |
| 404 | 传入了 `reference_name`，但标准动作库中不存在该动作 |

## 10. 图片静态姿态分析

```http
POST /motion/analyze-image
Content-Type: multipart/form-data
```

请求字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | file | 是 | 图片文件，支持 `.jpg`、`.jpeg`、`.png` |

处理流程：

```text
图片文件
  -> Pillow 解码为 RGB numpy array
  -> MediaPipe Pose 适配器提取关键点
  -> PoseSequence(T=1)
  -> 返回静态姿态摘要
```

响应示例：

```json
{
  "filename": "squat.png",
  "source_type": "image",
  "frames": 1,
  "joints": 33,
  "pose_model": "mediapipe_pose",
  "joint_schema": "mediapipe_33",
  "confidence_summary": {
    "mean": 0.91,
    "min": 0.72,
    "max": 0.99
  },
  "warnings": [
    "单张图片只能分析静态姿态，不能判断动作节奏、轨迹或发力顺序。"
  ],
  "message": "图片姿态已提取为 PoseSequence。当前返回静态姿态摘要；完整动作标准性判断需要视频序列或标准动作库对比。"
}
```

命令：

```bash
curl -X POST http://127.0.0.1:8000/motion/analyze-image \
  -F "file=@squat.png"
```

错误：

| 状态码 | 场景 |
|---|---|
| 422 | 文件为空、格式不支持、图片无法解码、未检测到人体姿态 |
| 503 | Pillow、MediaPipe 或 `pose_landmarker.task` 模型文件缺失 |

## 11. 视频姿态序列提取

```http
POST /motion/analyze-video
Content-Type: multipart/form-data
```

请求字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | file | 是 | 最大 30 MB 的 `.mp4`、`.mov` 或 `.avi` 短视频 |

当前处理流程：

```text
视频上传
  -> 临时文件（请求结束后删除）
  -> OpenCV 解码并按约 10 FPS 抽帧
  -> MediaPipe VIDEO 模式
  -> 最多处理 300 个采样帧
  -> PoseSequence(T=N, J=33, C=3)
  -> 返回有效帧率和置信度摘要
```

响应示例：

```json
{
  "filename": "squat.mp4",
  "source_type": "video",
  "frames": 15,
  "joints": 33,
  "fps": 7.5,
  "pose_model": "mediapipe_pose",
  "joint_schema": "mediapipe_33",
  "sampled_frames": 15,
  "valid_frame_ratio": 1.0,
  "confidence_summary": {"mean": 0.9926, "min": 0.9579, "max": 1.0},
  "warnings": [
    "当前仅验证视频到多帧 PoseSequence，不包含动作周期切分或标准动作评分。"
  ],
  "message": "视频已转换为多帧 PoseSequence。"
}
```

错误：

| 状态码 | 场景 |
|---|---|
| 413 | 视频超过 30 MB |
| 422 | 后缀不支持、无法解码或采样帧中未检测到人体 |
| 503 | OpenCV、MediaPipe 或 `pose_landmarker.task` 缺失 |

## 12. 意图路由规则

当前 Router 使用“加权规则 + 确定性歧义处理 + 语义样例 fallback + 可选本地 LLM classifier”。系统会扫描所有 intent 的短语和组合规则，识别顺序词、否定约束、跨域计划、plan-vs-motion、diet-vs-recipe 等 ambiguity signals；低置信或指定 review signal 才允许尝试 LLM。真实 Qwen provider 已接入，但 `LLM_ROUTER_ENABLED` 默认关闭。即使开启，LLM 也必须通过严格 JSON、合法 intent、非澄清、最低置信度，并且置信度高于当前规则才允许覆盖。

当前产品能力可以归纳为联网搜索、动作分析、饮食与菜谱、RAG 问答四类；代码为隔离营养建议与外部工具调用，保留 `diet` 和 `mcp` 两条路径，因此 API 可能返回五种 intent。

| Intent | 高权重示例 | 处理模块 |
|---|---|---|
| `search` | 搜索、查一下、联网、最新、新闻、最近 + 研究 | Search 子图 |
| `motion` | `.npz`、动作分析、姿势、深蹲 + 哪里不对、硬拉 + 姿势 | Motion 子图 |
| `diet` | 减脂、增肌、怎么吃、瘦一点、控制体重、饮食、热量 | Diet 子图 |
| `mcp` | 菜谱、烹饪、做法、番茄炒蛋、红烧肉、怎么做 + 菜名 | MCP 子图：工具发现、调用规划、JSON-RPC 工具调用、结果格式化 |
| `chat` | 低置信、纯知识解释、概念问题或无规则/语义样例命中 | Chat 子图 |

路由节点会在内部 `RouterState` 中记录 `_route_scores`、`_route_confidence`、`_route_reason`、`_route_source`、`_route_matches` 和 `_route_ambiguity_signals`。Phase 4.1 还会记录 `_primary_intent`、`_secondary_intents`、`_route_plan`、`_multi_intent_reason` 和 `_needs_clarification`；这些字段当前不作为 API 响应返回，公开响应中的 `intent` 始终等于主意图。评测脚本会额外输出 secondary intent 和 route plan 精确匹配率。`_route_source` 可能为 `weighted_rules`、`semantic_examples`、`llm_classifier` 或 `fallback`。

Phase 4 的执行层只允许四种两步组合：`search -> diet`、`search -> chat`、`motion -> chat`、`motion -> diet`。其他 route plan、需要澄清的请求仍只执行主意图。多步结果由 final synthesis 合并；部分子图失败时保留成功结果，全部失败时返回错误文本。SSE 和 WebSocket 对多步请求仍只进行一次最终流式生成，公开协议没有新增字段。

## 13. 状态码

| 状态码 | 说明 |
|---|---|
| 200 | 成功 |
| 422 | 请求参数校验失败，例如 `user_id` 或 `message` 为空/超长 |
| 413 | 上传视频超过大小限制 |
| 500 | 服务内部错误，例如模型加载失败、子图执行异常 |

## 14. 快速启动

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000/ui
```
