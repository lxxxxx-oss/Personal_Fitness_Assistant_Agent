# 微信小程序当前状态

本页是小程序唯一的当前状态入口。详细架构看 [DESIGN.md](./DESIGN.md)，早期任务拆解看 [PLAN.md](./PLAN.md)。

## 结论

小程序聊天端代码已经完成，支持五类 intent 展示、SSE 流式接收、非流式降级、历史记录和错误状态；当前主要缺口是真机/开发者工具端到端联调与体验优化。

| 模块 | 状态 | 说明 |
|---|---|---|
| 项目脚手架 | 已完成 | 原生小程序结构、配置、主题和本地存储 |
| API 封装 | 已完成 | health、chat、stream、history、clear |
| SSE 解析 | 已完成 | `enableChunked`、增量解析、token 更新 |
| Chat 页面 | 已完成 | 消息列表、意图展示、等待态、错误提示 |
| History 页面 | 已完成 | 加载、刷新、清空和空状态 |
| 复用组件 | 已完成 | message-bubble、intent-badge |
| 开发者工具联调 | 待验证 | 后端地址、流式分块、基础库兼容 |
| 真机与弱网 | 待验证 | 合法域名、HTTPS、超时与降级体验 |

## 已实现链路

```text
用户输入
  -> wx.request(enableChunked)
  -> SseParser
  -> meta 更新 intent
  -> token 增量渲染
  -> done 完成消息
  -> 失败时降级非流式或展示错误
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
| `POST /chat/stream` | SSE 对话 | 已实现 |
| `GET /chat/{user_id}/history` | 历史记录 | 已实现 |
| `DELETE /chat/{user_id}/history` | 清空历史 | 已实现 |

Motion 图片/视频上传目前只在 Web UI 和后端接口中提供，小程序尚未增加对应媒体选择控件。

## 下一步验收

1. 在微信开发者工具导入 `miniprogram/`，配置测试 AppID 和后端地址。
2. 验证五类 intent 的普通与流式响应。
3. 验证历史加载、清空、多轮记忆和断网提示。
4. 在支持 `enableChunked` 与不支持的基础库版本上分别验证。
5. 真机验证合法域名、HTTPS、弱网和长回复滚动性能。

## 运行提示

- 开发环境可在微信开发者工具中临时关闭合法域名校验。
- 真机与发布环境必须配置 HTTPS `request` 合法域名。
- 小程序端使用 `wx.request`，不受浏览器 CORS 机制限制。
