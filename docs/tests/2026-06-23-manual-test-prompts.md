# 手工体验测试语句

## 时间戳

2026-06-23

## 使用前提

后端启动：

```powershell
.\scripts\run_backend.cmd
```

访问地址：

```text
http://127.0.0.1:8000
```

说明：

- `scripts/run_backend.cmd` 默认设置 `MCP_SERVER_COMMAND=mock`，因此 MCP 菜谱工具不依赖真实 howtocook-mcp。
- 如果没有配置有效的 `MODEL_PATH`，涉及 LLM 生成的 `/chat`、`/chat/stream` 可能返回 `[Error: Model not loaded or prompt invalid]`。这说明路由链路被触发了，但本地模型不可用。
- `/health`、`/ui`、`/motion/analyze` 不依赖本地 LLM。

## 接口级测试

| 测试项 | 命令/地址 | 测试功能 | 正常结果 |
|---|---|---|---|
| 健康检查 | `http://127.0.0.1:8000/health` | FastAPI 服务是否启动 | 返回 `{"status":"ok","version":"0.1.0"}` |
| Web UI | `http://127.0.0.1:8000/ui` | 静态页面是否挂载 | 浏览器打开聊天页面 |
| 获取历史 | `GET /chat/u1/history` | 会话记忆接口 | 返回 `{"user_id":"u1","history":[...]}` |
| 清空历史 | `DELETE /chat/u1/history` | 清空会话记忆 | 返回 `{"user_id":"u1","status":"cleared"}` |

## 对话测试语句

以下语句可以在 Web UI 输入，也可以通过 `/chat` 接口发送。

| 输入语句 | 预期 intent | 测试功能 | 模型正常时应返回 |
|---|---|---|---|
| `你好，你能做什么？` | `chat` | 默认 Chat RAG fallback | 介绍健身助手能力，或基于知识库回答 |
| `如何做一个标准深蹲？` | `motion` | Motion 意图路由 | 如果没有 `.npz`，应说明深蹲技术要点和如何提供 3D 姿态数据 |
| `分析一下我的深蹲姿势` | `motion` | Motion 子图无文件 fallback | 不应瞎猜动作问题，应提示需要 `.npz` 姿态数据 |
| `减脂期间应该吃什么？` | `diet` | Diet 画像提取 + 营养 RAG | 给出减脂饮食原则、食物建议和餐次安排 |
| `我身高170体重80公斤，男性，想减脂，晚餐怎么吃？` | `diet` | 个性化饮食推荐 | 先总结用户画像，再给晚餐搭配建议 |
| `搜索一下最新的健身资讯` | `search` | Search 子图 + Tavily/mock | 有 Tavily Key 时返回搜索摘要和来源；无 Key 时返回 mock 搜索结果相关回答 |
| `查一下最近力量训练有什么新研究` | `search` | Query rewrite + 搜索合成 | 返回结构化要点和来源编号 |
| `怎么做番茄炒蛋？` | `mcp` | MCP 菜谱工具调用 | mock 模式下应返回番茄炒蛋配料和步骤 |
| `两个人吃，不知道吃什么` | `mcp` | MCP whatToEat 工具 | mock 模式下应推荐适合 2 人的菜品组合 |
| `帮我做一周膳食计划，3个人，虾过敏` | `mcp` | MCP recommendMeals 工具 | mock 模式下应返回一周计划和购物清单 |

## curl 示例

### Chat

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"u1\",\"message\":\"减脂期间应该吃什么？\"}"
```

正常响应结构：

```json
{
  "user_id": "u1",
  "intent": "diet",
  "reply": "...",
  "sources": []
}
```

### SSE 流式

```bash
curl -N -X POST http://127.0.0.1:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"u1\",\"message\":\"如何做一个标准深蹲？\"}"
```

正常事件流：

```text
event: meta
data: {"intent":"motion"}

data: ...

event: done
data: {}
```

## Motion 上传测试

项目中已生成体验用文件：

```text
tmp/sample_pose.npz
data/motions/squat.npz
```

基础分析：

```bash
curl -X POST http://127.0.0.1:8000/motion/analyze \
  -F "file=@tmp/sample_pose.npz"
```

正常结果：

```json
{
  "filename": "sample_pose.npz",
  "frames": 12,
  "joints": 17,
  "reference": null,
  "metrics": null,
  "message": "..."
}
```

标准动作对比：

```bash
curl -X POST http://127.0.0.1:8000/motion/analyze \
  -F "file=@tmp/sample_pose.npz" \
  -F "reference_name=squat"
```

正常结果：

```json
{
  "filename": "sample_pose.npz",
  "frames": 12,
  "joints": 17,
  "reference": "squat",
  "metrics": {
    "dtw_distance": 0.0,
    "cosine_similarity": 0.99,
    "shape_difference": 0.0,
    "labels": {
      "dtw": "优秀",
      "cosine": "优秀",
      "shape": "优秀"
    },
    "overall_verdict": "..."
  },
  "message": "姿态数据已加载，并完成与标准动作的相似度对比。"
}
```

## 异常测试

| 测试 | 命令/输入 | 正常结果 |
|---|---|---|
| 空消息 | `/chat` 中 `message=""` | HTTP 422 |
| 非 `.npz` 上传 | 上传 `sample.txt` 到 `/motion/analyze` | HTTP 422 |
| 不存在的标准动作 | `reference_name=unknown` | HTTP 404 |
| 清空历史后查询 | 先 DELETE 再 GET history | `history` 为空数组 |

