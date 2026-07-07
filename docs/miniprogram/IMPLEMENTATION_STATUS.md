# 微信小程序当前状态

本页是小程序唯一的当前状态入口。详细架构看 [DESIGN.md](./DESIGN.md)，早期任务拆解看 [PLAN.md](./PLAN.md)。

## 结论

小程序聊天端和 Motion 图片/视频上传闭环已经完成。用户通过统一媒体入口选择相册或相机，图片返回单帧姿态摘要；视频展示本地播放器、上传进度、多帧 PoseSequence 指标和真实执行标签。后端 WebSocket 已改为生成一个 token 就发送一个 token。当前主要缺口是微信开发者工具/真机端到端联调和体验优化。

| 模块 | 状态 | 说明 |
|---|---|---|
| 项目脚手架 | 已完成 | 原生小程序结构、配置、主题和本地存储 |
| API 封装 | 已完成 | health、chat、WebSocket、history、clear、Motion 图片/视频上传 |
| 流式接收 | 已完成 | WebSocket meta/token/done、后端真实逐 token 转发、端侧增量更新和 HTTP 降级 |
| Chat 页面 | 已完成 | 消息列表、意图展示、等待态、错误提示 |
| 回答元数据 | 已完成 | 展示后端透传的来源 URL 和非致命 warning，空数组时不占界面 |
| 执行模式可见性 | 已完成 | 展示 LLM、RAG、Search、MCP、Motion 的实际 mode；绿色为真实路径，黄色为 mock/fallback |
| Motion 图片上传 | 已完成 | `chooseMedia/chooseImage`、10MB 前置校验、`wx.uploadFile`、缩略图预览和结构化摘要 |
| Motion 视频上传 | 已完成 | `chooseMedia/chooseVideo`、30MB 校验、上传进度、本地播放和多帧摘要 |
| History 页面 | 已完成 | 加载、刷新、清空和空状态 |
| 复用组件 | 已完成 | message-bubble、intent-badge |
| 开发者工具联调 | 待验证 | 后端地址、流式分块、基础库兼容 |
| 真机与弱网 | 待验证 | 合法域名、HTTPS、超时与降级体验 |

## 已实现链路

```text
用户输入
  -> wx.connectSocket
  -> WebSocket meta 更新 intent / sources / warnings / execution
  -> token 增量渲染
  -> done 完成消息
  -> 建连或执行失败时降级 POST /chat
```

```text
用户主动选择图片
  -> 客户端校验大小（最大 10MB）
  -> 本地缩略图预览
  -> wx.uploadFile /motion/analyze-image
  -> MediaPipe 提取单帧关键点
  -> 展示 PoseSequence 摘要、置信度、warning 与 mediapipe_image 标签
```

```text
用户主动选择视频
  -> 客户端校验大小（最大 30MB）
  -> 本地 video 组件预览
  -> wx.uploadFile + onProgressUpdate
  -> OpenCV 抽帧 + MediaPipe VIDEO
  -> 展示有效帧、抽样帧、有效帧比例、FPS、置信度与 mediapipe_video 标签
```

支持展示的执行路径：

```text
chat / search / diet / motion / mcp
```

产品层可把 `diet` 和 `mcp` 统一归入“饮食与菜谱”，端侧标签仍展示实际执行路径。

## 后端依赖

| 接口 | 用途 | 后端状态 |
|---|---|---|
| `GET /health` | 连接检测 | 已实现 |
| `POST /chat` | 非流式降级 | 已实现 |
| `WebSocket /chat/ws` | 小程序主流式对话 | 已实现 |
| `GET /chat/{user_id}/history` | 历史记录 | 已实现 |
| `DELETE /chat/{user_id}/history` | 清空历史 | 已实现 |
| `POST /motion/analyze-image` | 动作图片上传与静态姿态提取 | 已接入小程序 |
| `POST /motion/analyze-video` | 动作视频上传与多帧姿态提取 | 已接入小程序 |

Motion 图片和视频均已接入小程序。视频结果目前只证明多帧姿态序列提取，不等于动作周期切分、标准动作匹配或动作质量评分。

## 下一步验收

1. 在微信开发者工具导入 `miniprogram/`，配置测试 AppID 和后端地址。
2. 验证图片/视频选择、预览、10MB/30MB 限制、上传进度和 413/422/503 错误提示。
3. 验证多帧结果中有效帧、抽样帧、FPS、置信度和 warning 的显示。
4. 验证五类 intent、历史记录、断网提示及 WebSocket/HTTP 降级。
5. 真机验证合法域名、HTTPS、隐私授权、弱网上传和长回复滚动性能。

## 运行提示

- 开发环境可在微信开发者工具中临时关闭合法域名校验。
- 真机与发布环境必须配置 HTTPS `request` 合法域名。
- 图片/视频上传还需要配置同一后端的 `uploadFile` 合法域名，并在发布前完成相册、相机和视频相关隐私声明与授权流程。
- 小程序端使用 `wx.request`，不受浏览器 CORS 机制限制。
