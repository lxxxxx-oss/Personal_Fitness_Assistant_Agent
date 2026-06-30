# 健身智能助手 — 微信小程序设计规范

> 过渡说明：当前小程序设计仍展示 `mcp` 菜谱意图，与现有代码保持一致。目标架构将菜谱并入 Diet；后端代码迁移时再同步删除相关标签、入口和联调用例。

**日期:** 2026-06-09  
**状态:** 待实施  
**关联文档:** [后端设计规范](../superpowers/specs/2026-06-09-fitness-assistant-design.md) | [后端 API 文档](../API.md)

---

## 1. 项目概述

为健身智能助手 Agent 开发微信小程序前端，复刻并增强现有 Web UI (`/ui`) 的聊天交互体验。小程序通过 HTTP + SSE 流式协议与后端 FastAPI 服务通信，支持五种意图路由的实时对话、对话历史管理、以及流式打字机效果的 token 级渲染。

### 1.1 与后端仓库关系

小程序代码放在同一仓库的 `miniprogram/` 目录下，与后端 `app/` 并列：

```
fitness-assistant/
├── app/                 # FastAPI 后端
├── miniprogram/         # 🆕 微信小程序前端
├── docs/                # 文档（含本设计规范）
├── data/                # 数据
└── tests/               # 测试
```

**互不影响：** 微信小程序运行在微信客户端内，只通过 HTTPS/WSS 请求后端 API，与后端代码在同一个 git 仓库中不产生任何运行时冲突。小程序开发工具仅关注 `miniprogram/` 目录下的文件。

---

## 2. 技术栈

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| 框架 | 微信小程序原生框架 | 无需第三方框架，降低体积和复杂度 |
| 语言 | JavaScript (ES6+) + WXML + WXSS | 小程序标准技术栈 |
| 网络请求 | `wx.request` + `enableChunked` | 非流式用标准请求，流式用分块传输 |
| SSE 解析 | 自定义 `SseParser` 工具类 | 手动解析 `text/event-stream` 格式 |
| 本地存储 | `wx.setStorageSync` / `wx.getStorageSync` | 持久化 userId 和服务地址 |
| 样式方案 | WXSS (CSS 子集) + rpx 单位 | 响应式适配不同屏幕 |
| 状态管理 | `app.globalData` + Page `data` | 轻量级，无需引入 Redux/MobX |

### 2.1 为什么不用第三方框架

- **体积限制：** 微信小程序主包限制 2MB，总包限制 20MB。不使用框架可以最大化有效代码空间
- **功能匹配：** 当前小程序功能聚焦于聊天交互，原生框架完全满足需求
- **维护成本：** 原生框架的 API 稳定，不依赖第三方库的更新

---

## 3. 项目结构

```
miniprogram/
├── pages/
│   ├── chat/                   # 主聊天页
│   │   ├── chat.js             # 页面逻辑 — SSE 流式消费、消息管理
│   │   ├── chat.json           # 页面配置 — 引用组件
│   │   ├── chat.wxml           # 页面模板 — 消息列表 + 输入区
│   │   └── chat.wxss           # 页面样式
│   └── history/                # 对话历史页
│       ├── history.js          # 历史记录加载与展示
│       ├── history.json
│       ├── history.wxml
│       └── history.wxss
├── components/
│   ├── message-bubble/         # 消息气泡组件
│   │   ├── message-bubble.js   # 属性: role, intent, content, isStreaming
│   │   ├── message-bubble.json
│   │   ├── message-bubble.wxml # 模板: 用户/助手两种样式, 打字机效果
│   │   └── message-bubble.wxss
│   └── intent-badge/           # 意图标签组件
│       ├── intent-badge.js     # 属性: intent, active
│       ├── intent-badge.json
│       ├── intent-badge.wxml
│       └── intent-badge.wxss
├── utils/
│   ├── api.js                  # API 请求封装 — 非流式 + 流式
│   ├── sse-parser.js           # SSE 流解析器 — 从分块数据中提取事件
│   ├── constants.js            # 常量 — intent 映射、配色、默认配置
│   └── storage.js              # 本地存储封装 — userId, 服务地址
├── app.js                      # 应用入口 — 初始化 userId, 健康检查
├── app.json                    # 应用配置 — 页面注册, 窗口样式, 权限
├── app.wxss                    # 全局样式 — 配色变量, 通用布局
├── project.config.json         # 微信开发者工具配置
└── sitemap.json                # 微信搜索索引配置
```

---

## 4. 页面与路由设计

### 4.1 页面注册

```json
// app.json
{
  "pages": [
    "pages/chat/chat",       // 首页 — 聊天界面
    "pages/history/history"  // 对话历史
  ],
  "window": {
    "navigationBarBackgroundColor": "#0f172a",
    "navigationBarTitleText": "健身助手",
    "navigationBarTextStyle": "white",
    "backgroundColor": "#0f172a"
  },
  "tabBar": {
    "color": "#94a3b8",
    "selectedColor": "#38bdf8",
    "backgroundColor": "#1e293b",
    "borderStyle": "black",
    "list": [
      {
        "pagePath": "pages/chat/chat",
        "text": "对话",
        "iconPath": "images/chat.png",
        "selectedIconPath": "images/chat-active.png"
      },
      {
        "pagePath": "pages/history/history",
        "text": "历史",
        "iconPath": "images/history.png",
        "selectedIconPath": "images/history-active.png"
      }
    ]
  }
}
```

### 4.2 路由导航

```
┌──────────────────────────────────────┐
│              Tab Bar                  │
│   [对话 (chat)]    [历史 (history)]    │
└──────────────────────────────────────┘
         │                    │
         ▼                    ▼
   chat 页面              history 页面
   - 消息列表             - 历史记录列表
   - 输入框               - 清空按钮
   - 意图标签栏           - 返回对话
   - 流式渲染
```

---

## 5. 组件设计

### 5.1 message-bubble — 消息气泡

**功能：** 渲染单条聊天消息，区分用户消息与助手消息，支持流式打字机效果。

**属性：**

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| role | String | `"user"` | `"user"` \| `"assistant"` |
| intent | String | `""` | 意图标签，仅 assistant 显示 |
| content | String | `""` | 消息文本内容 |
| isStreaming | Boolean | `false` | 是否处于流式渲染中（显示光标动画） |
| timestamp | Number | `0` | 消息时间戳 |

**视觉状态：**
- **用户消息：** 蓝色背景，右对齐，无意图标签
- **助手消息（已完成）：** 深色背景，左对齐，顶部显示意图标签
- **助手消息（流式中）：** 末尾显示闪烁光标 `▊`，内容实时增长
- **错误消息：** 红色边框，显示错误信息

**内部方法：**
- `stripThinkTags(content)` — 过滤 Qwen3 模型的 `<think>...</think>` 标签
- `formatContent(content)` — 处理换行和特殊字符

### 5.2 intent-badge — 意图标签

**功能：** 显示当前对话的意图分类，高亮活跃意图。

**属性：**

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| intent | String | `"chat"` | 意图标识 |
| active | Boolean | `false` | 是否高亮 |
| label | String | `""` | 显示文本（不传则自动映射） |
| size | String | `"small"` | `"small"` \| `"large"` |

**意图映射表：**

| intent | 标签 | 颜色 | 图标 |
|--------|------|------|------|
| chat | 知识问答 | #5eead4 | 💬 |
| search | 联网搜索 | #93c5fd | 🔍 |
| motion | 动作分析 | #c4b5fd | 🏃 |
| diet | 饮食推荐 | #fde68a | 🥗 |
| mcp | 菜谱查询 | #fca5a5 | 🍳 |

---

## 6. 数据流设计

### 6.1 用户 ID 管理

```
App 启动
  │
  ├── 检查 wx.getStorageSync('user_id')
  │     ├── 存在 → 使用已有 userId
  │     └── 不存在 → 生成新 userId，写入 Storage
  │
  └── 健康检查 GET /health → 更新连接状态
```

userId 格式: `wx_user_<timestamp>_<random6>` (如 `wx_user_1623456789_a3f2e1`)

### 6.2 对话流程

```
用户输入消息
  │
  ├── 1. 本地立即渲染用户消息气泡
  ├── 2. 创建空的助手消息气泡 (isStreaming=true)
  ├── 3. 发起 POST /chat/stream 请求 (enableChunked=true)
  │     ├── 收到 event:meta → 提取 intent → 更新意图标签
  │     ├── 收到 data:token → 追加到 content → setData 更新气泡
  │     ├── 收到 event:done → isStreaming=false → 移除光标
  │     └── 网络错误 → 显示错误信息 → 允许重试
  └── 4. 滚动到最新消息
```

### 6.3 非流式降级

当 `wx.request` 的 `enableChunked` 不可用或遇到问题时，降级为普通 POST `/chat`：

```
POST /chat (非流式)
  │
  ├── 1. 发送请求（含 loading 状态）
  ├── 2. 等待完整响应
  ├── 3. 一次性渲染完整回复
  └── 4. 更新 intent 标签
```

### 6.4 数据流图

```
┌──────────────┐    wx.request     ┌──────────────────┐
│   WXML View  │ ◄── setData ─── │   Page/Component │
│  (消息列表)   │                  │   (chat.js)      │
└──────────────┘                  └──────┬───────────┘
                                         │
                              ┌──────────┴───────────┐
                              │    utils/api.js       │
                              │  ┌─────────────────┐  │
                              │  │ streamChat()     │  │  enableChunked
                              │  │ chat()           │  │  POST /chat/stream
                              │  │ getHistory()     │  │  POST /chat
                              │  │ clearHistory()   │  │  GET/DELETE /history
                              │  │ healthCheck()    │  │  GET /health
                              │  └─────────────────┘  │
                              └──────────┬───────────┘
                                         │
                              ┌──────────┴───────────┐
                              │   utils/sse-parser.js │
                              │   解析 text/event-     │
                              │   stream 格式数据      │
                              └──────────────────────┘
```

---

## 7. SSE 流式解析器设计

### 7.1 问题

微信小程序的 `wx.request` 不支持浏览器标准的 `ReadableStream` / `EventSource` API。需要通过 `enableChunked: true` 参数启用分块传输，在 `onChunkReceived` 回调中手动拼接和解析 SSE 格式。

### 7.2 SseParser 类设计

```javascript
// utils/sse-parser.js

class SseParser {
  constructor() {
    this.buffer = '';       // 未完成行的缓冲区
    this.eventType = '';    // 当前事件类型
    this.callbacks = {
      onMeta: null,         // (intent: string) => void
      onToken: null,        // (token: string) => void
      onDone: null,         // () => void
      onError: null,        // (error: Error) => void
    };
  }

  // 喂入原始 chunk 数据（ArrayBuffer → string）
  feed(chunk) { /* ... */ }

  // 解析缓冲区中的完整行
  _parseLines() { /* ... */ }

  // 重置解析器状态
  reset() { /* ... */ }
}
```

### 7.3 SSE 解析流程

```
chunk 数据到达 (ArrayBuffer)
  │
  ├── ArrayBuffer → UTF-8 String
  ├── 拼接到 this.buffer
  ├── 按 \n 分割
  │     ├── 完整行 → _parseLines() 处理
  │     └── 不完整行 → 留在 buffer 等待下次拼接
  │
  └── _parseLines(line):
        ├── line === '' → 事件结束，触发回调
        ├── line.startsWith('event: meta') → eventType = 'meta'
        ├── line.startsWith('event: done') → eventType = 'done'
        ├── line.startsWith('data: ') → 提取 data
        │     ├── eventType === 'meta' → JSON.parse → onMeta(intent)
        │     ├── eventType === 'done' → onDone()
        │     └── 否则 → strip think tags → onToken(cleanToken)
        └── 其他 → 忽略
```

### 7.4 wx.request 分块配置

```javascript
const task = wx.request({
  url: `${API_BASE}/chat/stream`,
  method: 'POST',
  header: { 'Content-Type': 'application/json' },
  data: { user_id: userId, message: msg },
  enableChunked: true,  // 🔑 启用分块传输
  timeout: 120000,      // 2分钟超时（模型推理可能较慢）
});

// 监听分块数据
task.onChunkReceived((res) => {
  sseParser.feed(res.data);  // res.data 是 ArrayBuffer
});

// 请求完成
task.onHeadersReceived((res) => {
  // 检查 HTTP 状态码
});
```

---

## 8. API 层设计 (utils/api.js)

### 8.1 模块接口

```javascript
// utils/api.js

const API_BASE = 'http://127.0.0.1:8000';  // 开发环境（需配置域名白名单）

/**
 * 非流式对话 — POST /chat
 * @param {string} userId
 * @param {string} message
 * @returns {Promise<{intent: string, reply: string, sources: string[]}>}
 */
function chat(userId, message) { /* wx.request 封装 */ }

/**
 * 流式对话 — POST /chat/stream
 * @param {string} userId
 * @param {string} message
 * @param {object} callbacks - { onMeta, onToken, onDone, onError }
 * @returns {WechatMiniprogram.RequestTask} 可调用 .abort() 中止
 */
function streamChat(userId, message, callbacks) { /* wx.request + enableChunked */ }

/**
 * 获取历史 — GET /chat/{userId}/history
 * @returns {Promise<{history: Array<{role, content}>}>}
 */
function getHistory(userId) { /* ... */ }

/**
 * 清空历史 — DELETE /chat/{userId}/history
 * @returns {Promise<{status: string}>}
 */
function clearHistory(userId) { /* ... */ }

/**
 * 健康检查 — GET /health
 * @returns {Promise<{status: string, version: string}>}
 */
function healthCheck() { /* ... */ }

module.exports = { chat, streamChat, getHistory, clearHistory, healthCheck, API_BASE };
```

### 8.2 错误处理策略

| 错误类型 | HTTP 码 | 处理方式 |
|----------|---------|----------|
| 网络不可达 | — | 提示"无法连接服务器"，显示重试按钮 |
| 参数校验失败 | 422 | 提示具体字段错误 |
| 服务内部错误 | 500 | 提示"服务异常"，记录日志 |
| 超时 (120s) | — | 提示"响应超时"，允许重试 |
| chunk 解析失败 | — | 降级为非流式 `/chat` 请求 |

---

## 9. 样式设计

### 9.1 配色方案

与 Web UI 保持一致的暗色主题：

```css
/* 全局 CSS 变量 — 在 app.wxss 中定义 */
page {
  --bg-primary: #0f172a;      /* 主背景 — 深蓝黑 */
  --bg-secondary: #1e293b;    /* 次背景 — 卡片/侧栏 */
  --bg-tertiary: #334155;     /* 三级背景 — 输入框/分隔线 */
  --text-primary: #e2e8f0;    /* 主文字 — 浅灰白 */
  --text-secondary: #94a3b8;  /* 次文字 — 灰 */
  --text-muted: #64748b;      /* 弱文字 — 深灰 */
  --accent-blue: #2563eb;     /* 用户气泡 — 蓝 */
  --accent-cyan: #38bdf8;     /* 高亮色 — 青 */
  --accent-teal: #0f766e;     /* 活跃标签背景 */
  --accent-teal-text: #5eead4;/* 活跃标签文字 */
  --error: #ef4444;           /* 错误色 */
}
```

### 9.2 布局

```
┌─────────────────────────────────┐
│  Navigation Bar (暗色)           │
├─────────────────────────────────┤
│  Intent Badges Row (横向滚动)     │  ← 仅 chat 页
│  [知识问答] [联网搜索] [动作分析]   │
│  [饮食推荐] [菜谱查询]            │
├─────────────────────────────────┤
│                                 │
│  消息列表 (scroll-view)          │
│  ┌──────────────────────┐       │
│  │   用户消息 (右对齐)    │       │
│  └──────────────────────┘       │
│  ┌──────────────────┐           │
│  │ 助手消息 (左对齐)  │           │
│  │ [intent 标签]    │           │
│  └──────────────────┘           │
│  ┌──────────────────────┐       │
│  │   用户消息 (右对齐)    │       │
│  └──────────────────────┘       │
│         ...                      │
│                                 │
├─────────────────────────────────┤
│  Input Bar                      │
│  [输入框................] [发送]  │
└─────────────────────────────────┘
│  Tab Bar (暗色)                  │
│  [对话]  [历史]                  │
└─────────────────────────────────┘
```

### 9.3 rpx 适配

使用小程序的 rpx 响应式单位（750rpx = 屏幕宽度），自动适配不同手机屏幕。

---

## 10. 与后端 API 的适配

### 10.1 请求域名配置

小程序要求所有网络请求的目标域名必须在「小程序管理后台 → 开发 → 开发设置 → 服务器域名」中配置：

| 类型 | 开发环境 | 生产环境 |
|------|----------|----------|
| request 合法域名 | `http://127.0.0.1:8000` (开发工具不校验) | `https://your-domain.com` |
| socket 合法域名 | `wss://your-domain.com` (后续 WebSocket) | 同上 |

**开发阶段：** 微信开发者工具中勾选「不校验合法域名」可绕过此限制。

### 10.2 SSE 流格式对接

后端 `POST /chat/stream` 返回格式回顾：

```
event: meta
data: {"intent":"diet"}

data: 减脂

data: 期间

data: 建议

data: ...

event: done
data: {}
```

小程序 SseParser 需要处理：
- **meta 事件：** 只发一次，包含 `intent` 字段
- **token data：** 每条 `data:` 行可能包含 1 个或多个中文字符 / 英文单词
- **done 事件：** 流结束信号
- **Qwen3 think 标签：** `<think>...</think>` 需要在客户端过滤

### 10.3 响应模型映射

| 后端字段 | 小程序用途 |
|----------|-----------|
| `ChatResponse.user_id` | 回显验证（不展示） |
| `ChatResponse.intent` | 更新 intent-badge 高亮状态 |
| `ChatResponse.reply` | 消息气泡的 content |
| `ChatResponse.sources` | （后续版本）显示参考来源链接 |
| `HistoryResponse.history` | history 页的消息列表 |
| `HistoryResponse.user_id` | 回显验证 |

---

## 11. 特殊处理

### 11.1 Think 标签过滤

Qwen3 模型在推理过程中可能输出 `<think>...</think>` 标签包裹的内部推理文本，需要在客户端过滤：

```javascript
function stripThinkTags(text) {
  // 方法1: 正则移除完整的 think 块
  return text.replace(/<think>[\s\S]*?<\/think>/g, '');
  // 方法2: 流式场景下，实时去除未闭合的 <think> 起始标签
  // 在流式渲染中，维护一个状态标记 inThinkBlock
}
```

### 11.2 流式渲染性能

微信小程序的 `setData` 调用有频率限制。流式对话中 token 到达频率可能很高（数十个/秒），需要做节流处理：

```javascript
// 节流策略: 每 50ms 最多更新一次 UI
const THROTTLE_MS = 50;
let pendingContent = '';
let throttleTimer = null;

function onToken(token) {
  pendingContent += token;
  if (!throttleTimer) {
    throttleTimer = setTimeout(() => {
      this.setData({ content: pendingContent });
      pendingContent = '';
      throttleTimer = null;
    }, THROTTLE_MS);
  }
}
```

### 11.3 消息列表性能

长对话场景（>50条消息），使用 `scroll-view` 的虚拟列表或限制渲染条数以优化性能：

```xml
<scroll-view scroll-y enhanced show-scrollbar="{{false}}" 
             scroll-into-view="{{lastMsgId}}">
  <view wx:for="{{visibleMessages}}" wx:key="id">
    <message-bubble ... />
  </view>
</scroll-view>
```

通过只渲染最近 N 条消息（N=100）和 `scroll-into-view` 自动滚动到底部。

---

## 12. 后续扩展

| 功能 | 优先级 | 说明 |
|------|--------|------|
| WebSocket 流式 | Phase 2 | 替代 enableChunked 方案，更可靠的双向通信 |
| `/motion/analyze` 上传 | Phase 3 | 拍摄视频 / 选择 .npz 文件上传分析 |
| 参考来源展示 | Phase 2 | 展示 Search/Chat 子图返回的 sources 链接 |
| 离线缓存 | Phase 3 | 缓存知识库内容，减少重复请求 |
| 语音输入 | Phase 3 | 微信原生语音识别转文字 |
| 多语言 | Phase 4 | i18n 支持 |

---

## 13. 暂不纳入范围

- 用户登录/鉴权（当前依赖简单的 userId 机制）
- 推送通知
- 微信支付
- 运动数据同步（如微信运动步数）
- 小程序云开发（使用自有后端）
