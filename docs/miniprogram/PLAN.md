# 健身智能助手 — 微信小程序实施计划

> 过渡说明：本计划中的 `mcp` 菜谱页面和验收项对应当前代码。目标架构已经决定将菜谱并入 Diet，但在后端和小程序代码实际迁移前保留这些记录。

> **关联文档:** [小程序设计规范](./DESIGN.md) | [后端 API 文档](../API.md) | [后端实施计划](../superpowers/plans/2026-06-09-fitness-assistant-plan.md)

**目标:** 基于微信小程序原生框架，构建健身智能助手的移动端聊天界面，支持 SSE 流式对话、意图识别展示、对话历史管理。

**架构:** 双页面（chat + history）+ 两个可复用组件（message-bubble + intent-badge），通过 `utils/api.js` 封装后端 API 调用，`utils/sse-parser.js` 处理流式数据解析。

**技术栈:** 微信小程序原生框架 (JavaScript ES6+ / WXML / WXSS)，`wx.request` + `enableChunked` 实现 SSE 流式接收。

---

## 文件结构总览

```
miniprogram/
├── app.js                          # 应用入口
├── app.json                        # 应用配置
├── app.wxss                        # 全局样式
├── project.config.json             # 开发工具配置
├── sitemap.json                    # 搜索索引
├── images/                         # 图标资源
│   ├── chat.png
│   ├── chat-active.png
│   ├── history.png
│   └── history-active.png
├── pages/
│   ├── chat/
│   │   ├── chat.js
│   │   ├── chat.json
│   │   ├── chat.wxml
│   │   └── chat.wxss
│   └── history/
│       ├── history.js
│       ├── history.json
│       ├── history.wxml
│       └── history.wxss
├── components/
│   ├── message-bubble/
│   │   ├── message-bubble.js
│   │   ├── message-bubble.json
│   │   ├── message-bubble.wxml
│   │   └── message-bubble.wxss
│   └── intent-badge/
│       ├── intent-badge.js
│       ├── intent-badge.json
│       ├── intent-badge.wxml
│       └── intent-badge.wxss
└── utils/
    ├── api.js
    ├── sse-parser.js
    ├── constants.js
    └── storage.js
```

---

### Task 1: 项目脚手架 — 小程序项目初始化

**Files:**
- Create: `miniprogram/project.config.json`
- Create: `miniprogram/app.js`
- Create: `miniprogram/app.json`
- Create: `miniprogram/app.wxss`
- Create: `miniprogram/sitemap.json`
- Create: `miniprogram/utils/constants.js`
- Create: `miniprogram/utils/storage.js`

- [ ] **Step 1: 创建 project.config.json**

```json
{
  "description": "健身智能助手微信小程序",
  "packOptions": { "ignore": [], "include": [] },
  "setting": {
    "bundle": false,
    "userConfirmedBundleSwitch": false,
    "urlCheck": true,
    "coverView": true,
    "es6": true,
    "postcss": true,
    "minified": true,
    "enhance": true,
    "showShadowRootInWxmlPanel": true,
    "packNpmManually": false,
    "packNpmRelationList": [],
    "babelSetting": { "ignore": [], "disablePlugins": [], "outputPath": "" },
    "condition": false
  },
  "compileType": "miniprogram",
  "libVersion": "3.6.0",
  "appid": "wx0000000000000000",
  "projectname": "fitness-assistant",
  "condition": {},
  "editorSetting": { "tabIndent": "insertSpaces", "tabSize": 2 }
}
```

> **注意:** `appid` 需要替换为实际注册的小程序 AppID。开发阶段可用测试号。

- [ ] **Step 2: 创建 constants.js — 常量定义**

创建 `miniprogram/utils/constants.js`:

```javascript
/**
 * 全局常量定义.
 */

// 意图映射表
const INTENT_MAP = {
  chat:   { label: '知识问答', color: '#5eead4', icon: '💬', bgColor: '#0f766e' },
  search: { label: '联网搜索', color: '#93c5fd', icon: '🔍', bgColor: '#1e3a5f' },
  motion: { label: '动作分析', color: '#c4b5fd', icon: '🏃', bgColor: '#3b2f5e' },
  diet:   { label: '饮食推荐', color: '#fde68a', icon: '🥗', bgColor: '#5c4b1f' },
  mcp:    { label: '菜谱查询', color: '#fca5a5', icon: '🍳', bgColor: '#5c2d2d' },
};

// 意图列表（用于横向滚动标签栏）
const INTENT_LIST = [
  { key: 'chat',   label: '知识问答', icon: '💬' },
  { key: 'search', label: '联网搜索', icon: '🔍' },
  { key: 'motion', label: '动作分析', icon: '🏃' },
  { key: 'diet',   label: '饮食推荐', icon: '🥗' },
  { key: 'mcp',    label: '菜谱查询', icon: '🍳' },
];

// API 配置
const API_CONFIG = {
  baseUrl: 'http://127.0.0.1:8000',  // 开发环境
  timeout: 120000,                     // 2分钟超时
};

// 流式渲染节流间隔 (ms)
const STREAM_THROTTLE_MS = 50;

// 消息列表最大渲染条数
const MAX_VISIBLE_MESSAGES = 100;

module.exports = {
  INTENT_MAP,
  INTENT_LIST,
  API_CONFIG,
  STREAM_THROTTLE_MS,
  MAX_VISIBLE_MESSAGES,
};
```

- [ ] **Step 3: 创建 storage.js — 本地存储封装**

创建 `miniprogram/utils/storage.js`:

```javascript
/**
 * 本地存储封装 — 持久化 userId 和服务地址.
 */

const KEYS = {
  USER_ID: 'user_id',
  API_BASE: 'api_base_url',
};

/**
 * 获取或生成 userId.
 * 首次调用时生成唯一 ID 并持久化，后续调用返回已有 ID.
 */
function getUserId() {
  let userId = wx.getStorageSync(KEYS.USER_ID);
  if (!userId) {
    const ts = Date.now();
    const rand = Math.random().toString(36).slice(2, 8);
    userId = `wx_user_${ts}_${rand}`;
    wx.setStorageSync(KEYS.USER_ID, userId);
  }
  return userId;
}

/**
 * 获取 API 基础地址.
 */
function getApiBase() {
  const { API_CONFIG } = require('./constants');
  return wx.getStorageSync(KEYS.API_BASE) || API_CONFIG.baseUrl;
}

/**
 * 设置 API 基础地址.
 */
function setApiBase(url) {
  wx.setStorageSync(KEYS.API_BASE, url);
}

module.exports = {
  getUserId,
  getApiBase,
  setApiBase,
};
```

- [ ] **Step 4: 创建 app.js — 应用入口**

创建 `miniprogram/app.js`:

```javascript
/**
 * 健身智能助手 — 微信小程序入口.
 */
const { getUserId } = require('./utils/storage');
const { healthCheck } = require('./utils/api');

App({
  onLaunch() {
    // 初始化 userId
    this.globalData.userId = getUserId();

    // 健康检查
    healthCheck()
      .then((data) => {
        this.globalData.serverOnline = true;
        this.globalData.serverVersion = data.version;
        console.log(`[App] Server online, version: ${data.version}`);
      })
      .catch(() => {
        this.globalData.serverOnline = false;
        console.warn('[App] Server offline');
      });
  },

  globalData: {
    userId: '',
    serverOnline: false,
    serverVersion: '',
    currentIntent: 'chat',  // 当前对话的意图
  },
});
```

- [ ] **Step 5: 创建 app.json — 应用配置**

创建 `miniprogram/app.json`:

```json
{
  "pages": [
    "pages/chat/chat",
    "pages/history/history"
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
  },
  "style": "v2",
  "sitemapLocation": "sitemap.json"
}
```

- [ ] **Step 6: 创建 app.wxss — 全局样式**

创建 `miniprogram/app.wxss`:

```css
/* 全局 CSS 变量 */
page {
  --bg-primary: #0f172a;
  --bg-secondary: #1e293b;
  --bg-tertiary: #334155;
  --text-primary: #e2e8f0;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
  --accent-blue: #2563eb;
  --accent-cyan: #38bdf8;
  --accent-teal: #0f766e;
  --accent-teal-text: #5eead4;
  --error: #ef4444;

  background-color: var(--bg-primary);
  color: var(--text-primary);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 28rpx;
  line-height: 1.6;
  box-sizing: border-box;
}

/* 通用按钮重置 */
button {
  padding: 0;
  margin: 0;
  background: none;
  border: none;
  font-size: inherit;
  line-height: inherit;
}

button::after {
  border: none;
}
```

- [ ] **Step 7: 创建 sitemap.json**

```json
{
  "rules": [{
    "action": "allow",
    "page": "*"
  }]
}
```

- [ ] **Step 8: 创建占位图标**

在 `miniprogram/images/` 目录下放置 4 个 Tab 图标（可使用简单的纯色方块或 SVG 转换）。开发阶段可用占位图，后续替换正式图标。

- [ ] **Step 9: 验证**

- 在微信开发者工具中打开 `miniprogram/` 目录
- 确认项目编译成功，显示空白首页
- 确认 Tab Bar 正常显示

---

### Task 2: SSE 流式解析器 + API 封装

**Files:**
- Create: `miniprogram/utils/sse-parser.js`
- Create: `miniprogram/utils/api.js`

- [ ] **Step 1: 创建 SSE 解析器**

创建 `miniprogram/utils/sse-parser.js`:

```javascript
/**
 * SSE (Server-Sent Events) 流式解析器.
 * 
 * 用于解析 POST /chat/stream 返回的 text/event-stream 格式数据.
 * 配合 wx.request 的 enableChunked 使用.
 */

class SseParser {
  constructor(callbacks) {
    this.buffer = '';
    this.eventType = '';
    this.callbacks = {
      onMeta: callbacks.onMeta || null,
      onToken: callbacks.onToken || null,
      onDone: callbacks.onDone || null,
      onError: callbacks.onError || null,
    };
  }

  /**
   * 喂入原始 chunk 数据.
   * @param {ArrayBuffer} chunk - wx.onChunkReceived 回调的 res.data
   */
  feed(chunk) {
    try {
      // ArrayBuffer → UTF-8 String
      const text = this._arrayBufferToString(chunk);
      this.buffer += text;
      this._parseLines();
    } catch (err) {
      if (this.callbacks.onError) {
        this.callbacks.onError(err);
      }
    }
  }

  /**
   * 解析缓冲区中的完整行.
   */
  _parseLines() {
    const lines = this.buffer.split('\n');
    // 最后一行可能不完整，保留在 buffer
    this.buffer = lines.pop() || '';

    for (const line of lines) {
      this._processLine(line.trim());
    }
  }

  /**
   * 处理单行 SSE 数据.
   */
  _processLine(line) {
    // 空行 = 事件分隔符
    if (line === '') {
      if (this.eventType === 'meta') {
        // meta 事件在 data 行中已处理
      } else if (this.eventType === 'done') {
        if (this.callbacks.onDone) this.callbacks.onDone();
      }
      this.eventType = '';
      return;
    }

    // 事件类型行
    if (line.startsWith('event:')) {
      const type = line.slice(6).trim();
      this.eventType = type;
      return;
    }

    // 数据行
    if (line.startsWith('data:')) {
      const data = line.slice(5).trim();
      this._processData(data);
      return;
    }
  }

  /**
   * 处理 data 行内容.
   */
  _processData(data) {
    // meta 事件 — JSON 格式 {intent: "chat"}
    if (this.eventType === 'meta') {
      try {
        const meta = JSON.parse(data);
        if (this.callbacks.onMeta) this.callbacks.onMeta(meta);
      } catch (e) {
        // meta 解析失败，忽略
      }
      return;
    }

    // done 事件 — 空对象
    if (this.eventType === 'done') {
      return;
    }

    // 普通 token 数据 — 过滤 think 标签后回调
    const clean = this._stripThinkTags(data);
    if (clean && this.callbacks.onToken) {
      this.callbacks.onToken(clean);
    }
  }

  /**
   * 过滤 Qwen3 模型的 <think>...</think> 标签.
   * 流式场景下处理三种情况:
   *   1. 完整块: <think>text</think>
   *   2. 开头块: <think>text...
   *   3. 尾巴块: ...text</think>
   */
  _stripThinkTags(text) {
    // 移除完整的 think 块
    let result = text.replace(/<think>[\s\S]*?<\/think>/g, '');
    // 如果存在未闭合的 <think> (流式中间状态), 移除 <think> 及其后内容
    if (result.includes('<think>')) {
      result = result.replace(/<think>[\s\S]*$/, '');
    }
    // 如果存在未闭合的 </think> (残余), 移除
    if (result.includes('</think>')) {
      result = result.replace(/<\/think>/g, '');
    }
    return result;
  }

  /**
   * ArrayBuffer 转 UTF-8 字符串.
   */
  _arrayBufferToString(buffer) {
    // 微信小程序不支持 TextDecoder, 手动转换
    const uint8 = new Uint8Array(buffer);
    let result = '';
    // 批量处理避免栈溢出
    const CHUNK = 4096;
    for (let i = 0; i < uint8.length; i += CHUNK) {
      const slice = uint8.slice(i, i + CHUNK);
      result += String.fromCharCode.apply(null, slice);
    }
    return decodeURIComponent(escape(result));  // UTF-8 解码
  }

  /**
   * 重置解析器状态.
   */
  reset() {
    this.buffer = '';
    this.eventType = '';
  }
}

module.exports = { SseParser };
```

- [ ] **Step 2: 创建 API 封装**

创建 `miniprogram/utils/api.js`:

```javascript
/**
 * 后端 API 请求封装.
 */
const { getApiBase } = require('./storage');
const { API_CONFIG } = require('./constants');
const { SseParser } = require('./sse-parser');

/**
 * 通用 GET 请求.
 */
function _get(path) {
  const baseUrl = getApiBase();
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${baseUrl}${path}`,
      method: 'GET',
      timeout: 10000,
      success: (res) => {
        if (res.statusCode === 200) resolve(res.data);
        else reject(new Error(`HTTP ${res.statusCode}: ${JSON.stringify(res.data)}`));
      },
      fail: (err) => reject(new Error(`Network error: ${err.errMsg}`)),
    });
  });
}

/**
 * 通用 POST 请求.
 */
function _post(path, data, timeout = 30000) {
  const baseUrl = getApiBase();
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${baseUrl}${path}`,
      method: 'POST',
      header: { 'Content-Type': 'application/json' },
      data: data,
      timeout: timeout,
      success: (res) => {
        if (res.statusCode === 200) resolve(res.data);
        else reject(new Error(`HTTP ${res.statusCode}: ${JSON.stringify(res.data)}`));
      },
      fail: (err) => reject(new Error(`Network error: ${err.errMsg}`)),
    });
  });
}

/**
 * 健康检查 — GET /health.
 * @returns {Promise<{status: string, version: string}>}
 */
function healthCheck() {
  return _get('/health');
}

/**
 * 非流式对话 — POST /chat.
 * @param {string} userId
 * @param {string} message
 * @returns {Promise<{user_id: string, intent: string, reply: string, sources: string[]}>}
 */
function chat(userId, message) {
  return _post('/chat', { user_id: userId, message: message }, 120000);
}

/**
 * 流式对话 — POST /chat/stream (enableChunked).
 * @param {string} userId
 * @param {string} message
 * @param {object} callbacks - { onMeta, onToken, onDone, onError, onComplete }
 * @returns {WechatMiniprogram.RequestTask}
 */
function streamChat(userId, message, callbacks) {
  const baseUrl = getApiBase();
  const parser = new SseParser({
    onMeta: callbacks.onMeta,
    onToken: callbacks.onToken,
    onDone: () => {
      if (callbacks.onDone) callbacks.onDone();
    },
    onError: callbacks.onError,
  });

  const task = wx.request({
    url: `${baseUrl}/chat/stream`,
    method: 'POST',
    header: { 'Content-Type': 'application/json' },
    data: { user_id: userId, message: message },
    enableChunked: true,
    timeout: API_CONFIG.timeout,
    success: () => {
      // 请求成功完成（所有 chunk 已接收）
      if (callbacks.onComplete) callbacks.onComplete();
    },
    fail: (err) => {
      if (callbacks.onError) {
        callbacks.onError(new Error(`Request failed: ${err.errMsg}`));
      }
    },
  });

  // 监听分块数据
  task.onChunkReceived((res) => {
    try {
      parser.feed(res.data);
    } catch (e) {
      if (callbacks.onError) callbacks.onError(e);
    }
  });

  // 监听响应头（可用于提前获取状态码）
  task.onHeadersReceived((res) => {
    if (res.statusCode !== 200) {
      task.abort();
      if (callbacks.onError) {
        callbacks.onError(new Error(`HTTP ${res.statusCode}`));
      }
    }
  });

  return task;
}

/**
 * 获取对话历史 — GET /chat/{userId}/history.
 * @returns {Promise<{user_id: string, history: Array<{role: string, content: string}>}>}
 */
function getHistory(userId) {
  return _get(`/chat/${encodeURIComponent(userId)}/history`);
}

/**
 * 清空对话历史 — DELETE /chat/{userId}/history.
 * @returns {Promise<{user_id: string, status: string}>}
 */
function clearHistory(userId) {
  const baseUrl = getApiBase();
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${baseUrl}/chat/${encodeURIComponent(userId)}/history`,
      method: 'DELETE',
      timeout: 10000,
      success: (res) => {
        if (res.statusCode === 200) resolve(res.data);
        else reject(new Error(`HTTP ${res.statusCode}`));
      },
      fail: (err) => reject(new Error(`Network error: ${err.errMsg}`)),
    });
  });
}

module.exports = {
  healthCheck,
  chat,
  streamChat,
  getHistory,
  clearHistory,
};
```

- [ ] **Step 3: 验证**

```bash
# 在微信开发者工具中编译，确认无语法错误
# 可通过 App 面板查看 console.log 输出
# 确认 healthCheck 在 app.js 中被调用
```

---

### Task 3: message-bubble 组件

**Files:**
- Create: `miniprogram/components/message-bubble/message-bubble.js`
- Create: `miniprogram/components/message-bubble/message-bubble.json`
- Create: `miniprogram/components/message-bubble/message-bubble.wxml`
- Create: `miniprogram/components/message-bubble/message-bubble.wxss`

- [ ] **Step 1: 创建组件逻辑**

创建 `miniprogram/components/message-bubble/message-bubble.js`:

```javascript
/**
 * 消息气泡组件 — 渲染单条聊天消息.
 */
const { INTENT_MAP } = require('../../utils/constants');

Component({
  properties: {
    // 消息角色: 'user' | 'assistant'
    role: {
      type: String,
      value: 'user',
    },
    // 意图标识 (仅 assistant)
    intent: {
      type: String,
      value: '',
    },
    // 消息文本内容
    content: {
      type: String,
      value: '',
      observer: '_onContentChange',
    },
    // 是否流式渲染中
    isStreaming: {
      type: Boolean,
      value: false,
    },
    // 消息时间戳
    timestamp: {
      type: Number,
      value: 0,
    },
    // 是否为错误消息
    isError: {
      type: Boolean,
      value: false,
    },
    // 消息唯一 ID
    msgId: {
      type: String,
      value: '',
    },
  },

  data: {
    displayContent: '',    // 过滤 think 标签后的内容
    intentInfo: null,      // 意图映射信息
  },

  lifetimes: {
    attached() {
      this._updateDisplay();
    },
  },

  methods: {
    /**
     * 监听 content 变化，过滤并更新显示内容.
     */
    _onContentChange(newVal) {
      this._updateDisplay();
    },

    /**
     * 更新显示内容（过滤 think 标签，更新意图信息）.
     */
    _updateDisplay() {
      const cleanContent = this._stripThinkTags(this.properties.content);
      const intentInfo = this.properties.intent
        ? INTENT_MAP[this.properties.intent] || null
        : null;
      this.setData({
        displayContent: cleanContent,
        intentInfo: intentInfo,
      });
    },

    /**
     * 过滤 Qwen3 <think> 标签（非流式场景完整过滤）.
     */
    _stripThinkTags(text) {
      if (!text) return '';
      return text.replace(/<think>[\s\S]*?<\/think>/g, '').trim();
    },
  },
});
```

- [ ] **Step 2: 创建组件配置**

创建 `miniprogram/components/message-bubble/message-bubble.json`:

```json
{
  "component": true,
  "usingComponents": {}
}
```

- [ ] **Step 3: 创建组件模板**

创建 `miniprogram/components/message-bubble/message-bubble.wxml`:

```xml
<!-- 消息气泡组件模板 -->
<view class="bubble-wrapper {{role}} {{isError ? 'error' : ''}}" id="msg-{{msgId}}">
  <!-- 意图标签 (仅 assistant) -->
  <view class="intent-row" wx:if="{{role === 'assistant' && intentInfo}}">
    <text class="intent-tag" style="color: {{intentInfo.color}}; background: {{intentInfo.bgColor}};">
      {{intentInfo.icon}} {{intentInfo.label}}
    </text>
  </view>

  <!-- 消息内容 -->
  <view class="bubble {{role}}">
    <text class="content" wx:if="{{!isStreaming}}" selectable>{{displayContent}}</text>
    <text class="content streaming" wx:else>
      {{displayContent}}<text class="cursor">▊</text>
    </text>
  </view>

  <!-- 时间戳 -->
  <view class="timestamp" wx:if="{{timestamp && !isStreaming}}">
    <text>{{_formatTime(timestamp)}}</text>
  </view>
</view>
```

- [ ] **Step 4: 创建组件样式**

创建 `miniprogram/components/message-bubble/message-bubble.wxss`:

```css
.bubble-wrapper {
  display: flex;
  flex-direction: column;
  margin: 16rpx 24rpx;
  max-width: 85%;
}

.bubble-wrapper.user {
  align-self: flex-end;
  align-items: flex-end;
}

.bubble-wrapper.assistant {
  align-self: flex-start;
  align-items: flex-start;
}

.bubble-wrapper.error {
  border-left: 4rpx solid #ef4444;
}

/* 意图标签 */
.intent-row {
  margin-bottom: 8rpx;
}

.intent-tag {
  font-size: 22rpx;
  padding: 4rpx 16rpx;
  border-radius: 20rpx;
  display: inline-block;
}

/* 气泡 */
.bubble {
  padding: 20rpx 24rpx;
  border-radius: 16rpx;
  line-height: 1.6;
  font-size: 30rpx;
  word-break: break-word;
}

.bubble.user {
  background: #2563eb;
  color: #ffffff;
  border-bottom-right-radius: 4rpx;
}

.bubble.assistant {
  background: #1e293b;
  color: #e2e8f0;
  border: 1px solid #334155;
  border-bottom-left-radius: 4rpx;
}

.bubble.error {
  border-color: #ef4444;
}

/* 内容 */
.content {
  white-space: pre-wrap;
}

/* 流式光标 */
.cursor {
  animation: blink 1s step-end infinite;
  color: #38bdf8;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* 时间戳 */
.timestamp {
  margin-top: 8rpx;
  font-size: 22rpx;
  color: #64748b;
}
```

- [ ] **Step 5: 补充组件方法**

在 `message-bubble.js` 的 `methods` 中补充时间格式化方法：

```javascript
/**
 * 格式化时间戳为可读字符串.
 */
_formatTime(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
},
```

- [ ] **Step 6: 验证**

在微信开发者工具中创建测试页面或直接在 chat 页引用组件（Task 4），确认组件渲染正确。

---

### Task 4: intent-badge 组件

**Files:**
- Create: `miniprogram/components/intent-badge/intent-badge.js`
- Create: `miniprogram/components/intent-badge/intent-badge.json`
- Create: `miniprogram/components/intent-badge/intent-badge.wxml`
- Create: `miniprogram/components/intent-badge/intent-badge.wxss`

- [ ] **Step 1: 创建组件**

创建 `miniprogram/components/intent-badge/intent-badge.js`:

```javascript
/**
 * 意图标签组件.
 */
const { INTENT_MAP } = require('../../utils/constants');

Component({
  properties: {
    intent: {
      type: String,
      value: 'chat',
    },
    active: {
      type: Boolean,
      value: false,
    },
    size: {
      type: String,
      value: 'small',  // 'small' | 'large'
    },
  },

  data: {
    info: null,
  },

  lifetimes: {
    attached() {
      this._updateInfo();
    },
  },

  observers: {
    'intent'(newVal) {
      this._updateInfo();
    },
  },

  methods: {
    _updateInfo() {
      const info = INTENT_MAP[this.properties.intent] || INTENT_MAP.chat;
      this.setData({ info });
    },

    onTap() {
      this.triggerEvent('tap', { intent: this.properties.intent });
    },
  },
});
```

- [ ] **Step 2: 创建组件模板**

创建 `miniprogram/components/intent-badge/intent-badge.wxml`:

```xml
<view 
  class="badge {{active ? 'active' : ''}} {{size}}" 
  style="border-color: {{info.color}}; {{active ? 'background:' + info.bgColor + ';' : ''}}"
  bind:tap="onTap"
>
  <text class="icon" wx:if="{{size === 'large'}}">{{info.icon}}</text>
  <text class="label" style="color: {{active ? info.color : '#94a3b8'}}">{{info.label}}</text>
</view>
```

- [ ] **Step 3: 创建组件样式**

创建 `miniprogram/components/intent-badge/intent-badge.wxss`:

```css
.badge {
  display: inline-flex;
  align-items: center;
  gap: 6rpx;
  padding: 8rpx 20rpx;
  border-radius: 24rpx;
  border: 2rpx solid #334155;
  background: #1e293b;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.badge.active {
  border-width: 2rpx;
}

.badge.large {
  padding: 12rpx 28rpx;
}

.badge.large .icon {
  font-size: 28rpx;
}

.badge.large .label {
  font-size: 26rpx;
}

.icon {
  font-size: 22rpx;
}

.label {
  font-size: 22rpx;
  color: #94a3b8;
}
```

- [ ] **Step 4: 创建组件配置**

```json
{ "component": true, "usingComponents": {} }
```

---

### Task 5: chat 页面 — 主聊天界面

**Files:**
- Create: `miniprogram/pages/chat/chat.js`
- Create: `miniprogram/pages/chat/chat.json`
- Create: `miniprogram/pages/chat/chat.wxml`
- Create: `miniprogram/pages/chat/chat.wxss`

- [ ] **Step 1: 创建页面配置**

创建 `miniprogram/pages/chat/chat.json`:

```json
{
  "usingComponents": {
    "message-bubble": "/components/message-bubble/message-bubble",
    "intent-badge": "/components/intent-badge/intent-badge"
  },
  "navigationBarTitleText": "健身助手",
  "disableScroll": true
}
```

- [ ] **Step 2: 创建页面逻辑**

创建 `miniprogram/pages/chat/chat.js`:

```javascript
/**
 * chat 页面 — 主聊天界面.
 */
const { getUserId } = require('../../utils/storage');
const { streamChat, chat } = require('../../utils/api');
const { INTENT_LIST, STREAM_THROTTLE_MS, MAX_VISIBLE_MESSAGES } = require('../../utils/constants');

const app = getApp();

Page({
  data: {
    messages: [],           // 消息列表
    inputValue: '',         // 输入框内容
    isSending: false,       // 是否正在发送
    currentIntent: 'chat',  // 当前意图
    intentList: INTENT_LIST,// 意图标签列表
    scrollToId: '',         // 滚动目标消息 ID
    serverOnline: true,     // 服务器连接状态
    useStream: true,        // 是否使用流式（检测 enableChunked 支持）
    showRetry: false,       // 是否显示重试提示
  },

  onLoad() {
    const userId = getUserId();
    this.userId = userId;
    this.msgCounter = 0;
    this.streamTask = null;  // 当前流式请求任务

    // 检测 enableChunked 支持
    this._checkStreamSupport();

    // 添加欢迎消息
    this._addMessage('assistant', 
      '你好！我是你的健身智能助手。💪\n\n你可以问我：\n• 健身知识（如"如何做深蹲？"）\n• 饮食建议（如"减脂期间吃什么？"）\n• 动作分析（如"分析深蹲姿势"）\n• 菜谱查询（如"怎么做番茄炒蛋？"）\n• 联网搜索（如"搜索最新健身资讯"）',
      'chat'
    );
  },

  onUnload() {
    // 页面卸载时中止流式请求
    if (this.streamTask) {
      this.streamTask.abort();
    }
  },

  /**
   * 检测流式功能支持.
   */
  _checkStreamSupport() {
    // enableChunked 在基础库 2.20.1+ 支持
    const systemInfo = wx.getSystemInfoSync();
    const SDKVersion = systemInfo.SDKVersion;
    const [major, minor] = SDKVersion.split('.').map(Number);
    const supported = major > 2 || (major === 2 && minor >= 20);
    if (!supported) {
      console.warn('[Chat] enableChunked not supported, using non-stream mode');
      this.setData({ useStream: false });
    }
  },

  /**
   * 输入框内容变化.
   */
  onInput(e) {
    this.setData({ inputValue: e.detail.value });
  },

  /**
   * 发送消息.
   */
  sendMessage() {
    const msg = this.data.inputValue.trim();
    if (!msg || this.data.isSending) return;

    this.setData({ inputValue: '', isSending: true, showRetry: false });

    // 添加用户消息
    this._addMessage('user', msg);

    if (this.data.useStream) {
      this._sendStream(msg);
    } else {
      this._sendNonStream(msg);
    }
  },

  /**
   * 流式发送.
   */
  _sendStream(msg) {
    // 创建助手消息占位
    const assistantId = this._addMessage('assistant', '', '', true);

    let fullContent = '';
    let pendingContent = '';
    let throttleTimer = null;
    let intent = '';

    const updateUI = () => {
      fullContent += pendingContent;
      pendingContent = '';
      throttleTimer = null;
      this._updateMessage(assistantId, fullContent, intent, true);
    };

    this.streamTask = streamChat(this.userId, msg, {
      onMeta: (meta) => {
        intent = meta.intent || 'chat';
        this.setData({ currentIntent: intent });
        this._updateMessage(assistantId, fullContent, intent, true);
      },

      onToken: (token) => {
        pendingContent += token;
        if (!throttleTimer) {
          throttleTimer = setTimeout(updateUI, STREAM_THROTTLE_MS);
        }
      },

      onDone: () => {
        // 清空剩余内容
        if (throttleTimer) {
          clearTimeout(throttleTimer);
          updateUI();
        }
        // 再次过滤 think 标签
        const cleaned = fullContent.replace(/<think>[\s\S]*?<\/think>/g, '').trim();
        this._updateMessage(assistantId, cleaned, intent, false);
        this.setData({ isSending: false });
        this.streamTask = null;
        this._scrollToBottom();
      },

      onError: (err) => {
        console.error('[Chat] Stream error:', err.message);
        if (throttleTimer) {
          clearTimeout(throttleTimer);
          updateUI();
        }
        const errorMsg = fullContent || `❌ 网络错误: ${err.message}`;
        this._updateMessage(assistantId, errorMsg, intent, false, true);
        this.setData({ isSending: false, showRetry: true });
        this.streamTask = null;
      },

      onComplete: () => {
        // 请求完全结束
      },
    });
  },

  /**
   * 非流式发送 (降级方案).
   */
  async _sendNonStream(msg) {
    const assistantId = this._addMessage('assistant', '思考中...', 'chat', true);

    try {
      const result = await chat(this.userId, msg);
      this._updateMessage(assistantId, result.reply, result.intent, false);
      this.setData({ currentIntent: result.intent });
    } catch (err) {
      this._updateMessage(assistantId, `❌ ${err.message}`, 'chat', false, true);
      this.setData({ showRetry: true });
    }

    this.setData({ isSending: false });
    this._scrollToBottom();
  },

  /**
   * 重试发送.
   */
  retrySend() {
    // 移除最后一条错误消息
    const messages = this.data.messages;
    if (messages.length > 0 && messages[messages.length - 1].isError) {
      messages.pop();
      this.setData({ messages });
    }
    this.setData({ showRetry: false });
  },

  /**
   * 添加消息到列表.
   * @returns {string} 消息唯一 ID
   */
  _addMessage(role, content, intent = '', isStreaming = false) {
    const id = `msg_${this.msgCounter++}`;
    const msg = {
      id,
      role,
      content,
      intent,
      isStreaming,
      isError: false,
      timestamp: Date.now(),
    };
    const messages = [...this.data.messages, msg];
    // 限制渲染条数
    if (messages.length > MAX_VISIBLE_MESSAGES) {
      messages.splice(0, messages.length - MAX_VISIBLE_MESSAGES);
    }
    this.setData({ messages, scrollToId: id });
    return id;
  },

  /**
   * 更新指定消息.
   */
  _updateMessage(id, content, intent = '', isStreaming = false, isError = false) {
    const messages = this.data.messages.map(m => {
      if (m.id === id) {
        return { ...m, content, intent, isStreaming, isError, timestamp: Date.now() };
      }
      return m;
    });
    this.setData({ messages });
  },

  /**
   * 滚动到底部.
   */
  _scrollToBottom() {
    const lastMsg = this.data.messages[this.data.messages.length - 1];
    if (lastMsg) {
      this.setData({ scrollToId: lastMsg.id });
    }
  },

  /**
   * 清空对话.
   */
  clearChat() {
    wx.showModal({
      title: '清空对话',
      content: '确定要清空当前对话吗？',
      success: (res) => {
        if (res.confirm) {
          this.setData({ messages: [] });
        }
      },
    });
  },
});
```

- [ ] **Step 3: 创建页面模板**

创建 `miniprogram/pages/chat/chat.wxml`:

```xml
<view class="chat-container">
  <!-- 意图标签栏 -->
  <view class="intent-bar">
    <scroll-view scroll-x enhanced show-scrollbar="{{false}}" class="intent-scroll">
      <view class="intent-list">
        <intent-badge 
          wx:for="{{intentList}}" 
          wx:key="key"
          intent="{{item.key}}"
          active="{{item.key === currentIntent}}"
          size="small"
          bind:tap="onIntentTap"
        />
      </view>
    </scroll-view>
  </view>

  <!-- 消息列表 -->
  <scroll-view 
    class="message-list" 
    scroll-y 
    enhanced 
    show-scrollbar="{{false}}"
    scroll-into-view="{{scrollToId}}"
    scroll-with-animation
  >
    <view class="message-container">
      <message-bubble 
        wx:for="{{messages}}" 
        wx:key="id"
        role="{{item.role}}"
        intent="{{item.intent}}"
        content="{{item.content}}"
        isStreaming="{{item.isStreaming}}"
        isError="{{item.isError}}"
        timestamp="{{item.timestamp}}"
        msgId="{{item.id}}"
      />
    </view>

    <!-- 底部占位，确保最后一条消息不被输入栏遮挡 -->
    <view class="bottom-spacer"></view>
  </scroll-view>

  <!-- 输入栏 -->
  <view class="input-bar safe-area-bottom">
    <input 
      class="msg-input"
      type="text"
      value="{{inputValue}}"
      placeholder="输入你的问题..."
      placeholder-class="input-placeholder"
      bindinput="onInput"
      bindconfirm="sendMessage"
      confirm-type="send"
      disabled="{{isSending}}"
      maxlength="1000"
      cursor-spacing="20"
    />
    <button 
      class="send-btn {{inputValue ? 'active' : ''}}"
      bindtap="sendMessage"
      disabled="{{!inputValue || isSending}}"
    >
      {{isSending ? '...' : '发送'}}
    </button>
  </view>

  <!-- 重试提示 -->
  <view class="retry-banner" wx:if="{{showRetry}}" bindtap="retrySend">
    <text>⚠️ 网络连接异常，点击重试</text>
  </view>
</view>
```

- [ ] **Step 4: 创建页面样式**

创建 `miniprogram/pages/chat/chat.wxss`:

```css
.chat-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #0f172a;
}

/* 意图标签栏 */
.intent-bar {
  background: #1e293b;
  border-bottom: 1px solid #334155;
  padding: 16rpx 0;
}

.intent-scroll {
  width: 100%;
  white-space: nowrap;
}

.intent-list {
  display: inline-flex;
  gap: 12rpx;
  padding: 0 20rpx;
}

/* 消息列表 */
.message-list {
  flex: 1;
  overflow-y: auto;
}

.message-container {
  display: flex;
  flex-direction: column;
  padding: 16rpx 0;
}

.bottom-spacer {
  height: 32rpx;
}

/* 输入栏 */
.input-bar {
  display: flex;
  align-items: center;
  gap: 16rpx;
  padding: 16rpx 24rpx;
  background: #1e293b;
  border-top: 1px solid #334155;
}

.msg-input {
  flex: 1;
  height: 76rpx;
  padding: 0 24rpx;
  border-radius: 38rpx;
  border: 1px solid #334155;
  background: #0f172a;
  color: #e2e8f0;
  font-size: 30rpx;
}

.input-placeholder {
  color: #64748b;
}

.send-btn {
  width: 120rpx;
  height: 76rpx;
  border-radius: 38rpx;
  background: #334155;
  color: #64748b;
  font-size: 28rpx;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}

.send-btn.active {
  background: #2563eb;
  color: #ffffff;
}

.send-btn[disabled] {
  opacity: 0.6;
}

/* 重试横幅 */
.retry-banner {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  background: #ef4444;
  color: white;
  text-align: center;
  padding: 16rpx;
  font-size: 26rpx;
  z-index: 100;
}

/* 安全区域适配 */
.safe-area-bottom {
  padding-bottom: constant(safe-area-inset-bottom);
  padding-bottom: env(safe-area-inset-bottom);
}
```

- [ ] **Step 5: 验证**

- 在开发者工具中测试发送消息
- 验证消息气泡显示正确
- 验证意图标签高亮
- 验证流式打字机效果
- 验证输入框清空和发送按钮状态

---

### Task 6: history 页面 — 对话历史

**Files:**
- Create: `miniprogram/pages/history/history.js`
- Create: `miniprogram/pages/history/history.json`
- Create: `miniprogram/pages/history/history.wxml`
- Create: `miniprogram/pages/history/history.wxss`

- [ ] **Step 1: 创建页面逻辑**

创建 `miniprogram/pages/history/history.js`:

```javascript
/**
 * history 页面 — 对话历史查看.
 */
const { getUserId } = require('../../utils/storage');
const { getHistory, clearHistory } = require('../../utils/api');
const { INTENT_MAP } = require('../../utils/constants');

Page({
  data: {
    history: [],         // 历史消息列表
    isEmpty: true,       // 是否为空
    isLoading: true,     // 加载中
    error: '',           // 错误信息
  },

  onShow() {
    this.loadHistory();
  },

  /**
   * 加载对话历史.
   */
  async loadHistory() {
    this.setData({ isLoading: true, error: '' });

    try {
      const userId = getUserId();
      const result = await getHistory(userId);
      const history = result.history || [];
      this.setData({
        history,
        isEmpty: history.length === 0,
        isLoading: false,
      });
    } catch (err) {
      this.setData({
        isLoading: false,
        error: err.message,
      });
    }
  },

  /**
   * 清空历史.
   */
  async onClearHistory() {
    wx.showModal({
      title: '清空历史',
      content: '确定要清空所有对话历史吗？此操作不可撤销。',
      confirmColor: '#ef4444',
      success: async (res) => {
        if (res.confirm) {
          try {
            const userId = getUserId();
            await clearHistory(userId);
            this.setData({ history: [], isEmpty: true });
            wx.showToast({ title: '已清空', icon: 'success' });
          } catch (err) {
            wx.showToast({ title: '清空失败', icon: 'error' });
          }
        }
      },
    });
  },

  /**
   * 下拉刷新.
   */
  onPullDownRefresh() {
    this.loadHistory().finally(() => {
      wx.stopPullDownRefresh();
    });
  },
});
```

- [ ] **Step 2: 创建页面模板**

创建 `miniprogram/pages/history/history.wxml`:

```xml
<view class="history-container">
  <!-- 加载中 -->
  <view class="status-message" wx:if="{{isLoading}}">
    <text>加载中...</text>
  </view>

  <!-- 错误 -->
  <view class="status-message error" wx:elif="{{error}}">
    <text>加载失败: {{error}}</text>
    <button class="retry-btn" bindtap="loadHistory">重试</button>
  </view>

  <!-- 空状态 -->
  <view class="status-message" wx:elif="{{isEmpty}}">
    <text class="empty-icon">📭</text>
    <text>暂无对话历史</text>
    <text class="empty-hint">去"对话"页面开始和助手聊天吧</text>
  </view>

  <!-- 历史列表 -->
  <scroll-view class="history-list" scroll-y wx:else>
    <view class="history-item" wx:for="{{history}}" wx:key="index">
      <view class="role-tag {{item.role}}">
        {{item.role === 'user' ? '👤 你' : '🤖 助手'}}
      </view>
      <view class="history-content">{{item.content}}</view>
    </view>
  </scroll-view>

  <!-- 清空按钮 (固定底部) -->
  <view class="clear-bar" wx:if="{{!isEmpty && !isLoading}}">
    <button class="clear-btn" bindtap="onClearHistory">清空全部历史</button>
  </view>
</view>
```

- [ ] **Step 3: 创建页面样式**

创建 `miniprogram/pages/history/history.wxss`:

```css
.history-container {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: #0f172a;
  padding-bottom: 100rpx;
}

/* 状态消息 */
.status-message {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16rpx;
  padding: 80rpx 40rpx;
  color: #94a3b8;
  font-size: 28rpx;
}

.status-message.error {
  color: #ef4444;
}

.empty-icon {
  font-size: 72rpx;
  margin-bottom: 16rpx;
}

.empty-hint {
  color: #64748b;
  font-size: 24rpx;
}

.retry-btn {
  margin-top: 24rpx;
  padding: 16rpx 48rpx;
  background: #1e293b;
  color: #e2e8f0;
  border-radius: 12rpx;
  border: 1px solid #334155;
  font-size: 26rpx;
}

/* 历史列表 */
.history-list {
  flex: 1;
  padding: 24rpx;
}

.history-item {
  margin-bottom: 24rpx;
  padding: 20rpx 24rpx;
  background: #1e293b;
  border-radius: 12rpx;
  border: 1px solid #334155;
}

.role-tag {
  font-size: 22rpx;
  color: #94a3b8;
  margin-bottom: 8rpx;
}

.role-tag.user {
  color: #93c5fd;
}

.role-tag.assistant {
  color: #5eead4;
}

.history-content {
  font-size: 28rpx;
  color: #e2e8f0;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 清空栏 */
.clear-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 20rpx 24rpx;
  background: #1e293b;
  border-top: 1px solid #334155;
  padding-bottom: constant(safe-area-inset-bottom);
  padding-bottom: env(safe-area-inset-bottom);
}

.clear-btn {
  width: 100%;
  padding: 20rpx;
  background: transparent;
  color: #ef4444;
  border: 1px solid #ef4444;
  border-radius: 12rpx;
  font-size: 28rpx;
  text-align: center;
}
```

- [ ] **Step 4: 创建页面配置**

```json
{
  "usingComponents": {},
  "navigationBarTitleText": "对话历史",
  "enablePullDownRefresh": true,
  "backgroundColor": "#0f172a",
  "backgroundTextStyle": "light"
}
```

---

### Task 7: 端到端集成验证 + 调试

- [ ] **Step 1: 启动后端服务**

```bash
cd D:/Users/Agent/Personal_Fitness_Assistant_Agent
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: 在微信开发者工具中验证**

测试清单:
- [ ] 小程序启动 → App onLaunch → 健康检查通过
- [ ] chat 页面 → 欢迎消息显示
- [ ] 输入"如何做深蹲？" → 流式返回 → 意图=chat → 内容正确
- [ ] 输入"减脂期间吃什么？" → 意图=diet → 标签高亮为饮食推荐
- [ ] 输入"搜索最新健身资讯" → 意图=search → 标签高亮
- [ ] 输入"怎么做番茄炒蛋？" → 意图=mcp → 菜谱内容返回
- [ ] 发送多轮对话 → 上下文记忆生效
- [ ] history 页面 → 显示对话历史
- [ ] 清空历史 → 再次加载为空
- [ ] 断网测试 → 错误提示显示 → 重试按钮可用
- [ ] 流式降级测试 → 非流式模式正常

- [ ] **Step 3: 修复发现的问题**

根据测试结果修复 bug，达到全部清单项通过。

---

### Task 8: 优化与 polish

- [ ] **Step 1: 流式渲染性能优化**

验证 50ms 节流间隔是否流畅，根据实际效果调整。

- [ ] **Step 2: 消息列表长列表优化**

测试 100+ 条消息时的滚动性能，必要时限制 `wx:for` 渲染数量。

- [ ] **Step 3: 图标资源替换**

用正式的 SVG/PNG 图标替换占位图。

- [ ] **Step 4: 暗色主题一致性检查**

确认所有页面和组件统一使用暗色主题，无白色闪烁。

- [ ] **Step 5: 安全区域适配**

确认 iPhone X 等设备的底部安全区域正常显示。

- [ ] **Step 6: 小程序包体积检查**

在开发者工具中查看代码包大小，确保主包 < 2MB。

---

### Task 9: 提交

- [ ] **Step 1: 提交代码**

```bash
git add miniprogram/ docs/miniprogram/
git commit -m "feat: add WeChat miniprogram frontend with SSE streaming chat"
```

- [ ] **Step 2: 更新项目根目录说明**（可选）

在项目中适当位置添加小程序入口说明。
