# 上下文渐进式压缩设计

> **定位说明**：本文档设计的是上下文压缩管道（prompt 组装前的取舍与注入策略）。底层记忆存储（`SlidingWindowMemory`、`_sessions`、`_structured_state`）作为压缩层的数据来源，在本设计中引用但不改动其存储机制。
>
> 上下文压缩 ≠ 记忆系统。记忆系统决定存什么、存多久、怎么存；上下文压缩决定进 prompt 时带什么、怎么压缩、怎么拼接。

## 1. 现状诊断

### 1.1 当前记忆机制

| 组件 | 当前行为 |
|---|---|
| 存储 | `SlidingWindowMemory`，基于 `collections.deque`，`max_turns=6`（12 条消息），FIFO 淘汰 |
| 会话隔离 | `_sessions: Dict[str, SlidingWindowMemory]`，按 `user_id` 隔离，纯进程内存，重启丢失 |
| 消费方 | **仅 Chat 子图**读取 memory，且只取 `memory[-6:]`（最后 6 条 ≈ 3 轮） |
| 压缩 | **无**。超过 6 轮直接丢弃，没有摘要、提炼或嵌入化 |

### 1.2 各子图 memory 使用现状

| 子图 | 读 memory | 写 memory | 说明 |
|---|---|---|---|
| Chat | ✅ `memory[-6:]` | ❌ 不写，只靠 `main.py` 的 `add_turn()` | 注入 Prompt "对话历史" 段落 |
| Diet | ❌ | ❌ | 不上传上下文，上一轮说"素食者"下一轮不知道 |
| Search | ❌ | ❌ | 无跨轮上下文 |
| Motion | ❌ | ❌ | 无跨轮上下文 |
| MCP | ❌ | ❌ | 无跨轮上下文 |

### 1.3 硬约束

- `MAX_PROMPT_CHARS = 8192`（`app/llm/loader.py`），超出直接拒绝
- 单进程模型生成全局串行锁 `_MODEL_GENERATION_LOCK`
- 记忆条目仅 `{role, content}`，无时间戳或元数据

---

## 2. 设计目标

1. **渐进式压缩**：保留最近 6 轮原文，6 轮之外的历史 → 结构化提取后丢弃原文
2. **全局覆盖**：所有子图（Chat/Diet/Search/Motion/MCP）统一受益于压缩后的状态
3. **代码规则为主**：子图执行时由代码直接写入结构化字段，LLM 只做兜底提取
4. **可观测**：压缩发生时在对话流中插入系统消息气泡，用户可点击展开查看状态
5. **安全约束永不被截断**：规则写入磁盘 + 代码固定注入 Prompt 最前端

---

## 3. 触发机制

### 3.1 混合触发策略

```
最近 6 轮原文始终保留
  +
总 context 超过 token 阈值时触发压缩
  →
6 轮以外的历史 → 结构化提取后丢弃原文
```

### 3.2 Token 阈值

| 参数 | 值 | 说明 |
|---|---|---|
| `COMPACT_TRIGGER_CHARS` | **6000** | 拼接后 prompt 超过此值触发压缩 |
| 模型上下文窗口 | 8192 chars（`MAX_PROMPT_CHARS`） | Qwen3-0.6B |
| 生成预留 | 1024 tokens（`max_new_tokens`） | 留给 LLM 回答的空间 |
| 安全余量 | ~1168 chars | 避免压缩后 prompt 仍然超限 |

触发检查点：**每次构建 prompt 的节点**（子图 `generate_node`）在拼接前做判断。

---

## 4. 结构化状态 Schema

### 4.1 字段定义

所有字段存储在 `RouterState._structured_state` 中，类型为 `Dict[str, Any]`：

| 字段 | 类型 | 写入方式 | 写入方 | 说明 |
|---|---|---|---|---|
| `task` | `List[str]` | 代码规则 | Router 节点 | 最近 N 轮的 intent + execution_plan |
| `files` | `List[Dict]` | 代码规则 | Motion API / 子图 | 用户上传的图片/视频文件名、类型、帧数 |
| `errors` | `List[Dict]` | 代码规则 | 各子图 | ToolResult 失败记录（error_code + component） |
| `decisions` | `List[Dict]` | 代码规则 | Router 节点 | Router 决策（source / intent / confidence） |
| `todos` | `List[str]` | LLM 兜底提取 | 压缩触发时 | 用户明确要求但未完成的事项 |
| `profile` | `Dict` | 代码规则 | Diet 子图 | 用户画像（身高/体重/性别/目标/偏好），覆盖式更新 |
| `knowledge_sources` | `List[str]` | 代码规则 | Chat/Diet 子图 | 已引用过的 RAG 知识来源标识，去重 |
| `tool_results_summary` | `Dict[str, str]` | 代码规则 | Search/MCP 子图 | 每个工具最近一次结果摘要（<500 字符） |
| `user_context` | `List[str]` | LLM 兜底提取 | 压缩触发时 | 用户在对话中透露的关键事实（如"膝盖不适"、"素食者"），模板驱动 |

### 4.2 字段上限（防自膨胀）

| 字段 | 上限 |
|---|---|
| `task` | 保留最近 **10 条** |
| `files` | 保留最近 **5 个** |
| `errors` | 保留最近 **5 条** |
| `decisions` | 保留最近 **5 条** |
| `todos` | 保留最近 **5 条** |
| `user_context` | 保留最近 **10 条**，去重 |
| `knowledge_sources` | 保留最近 **20 条**，去重 |
| `tool_results_summary` | 每个工具只保留**最近一次**结果 |
| `profile` | **覆盖式更新**（不追加） |

### 4.3 user_context 的重要性

结构化字段主要捕获**系统行为**（错误/决策/文件），但用户可能在对话中透露关键信息：
- "我膝盖有点疼"
- "我是素食者"
- "最近在备考没时间去健身房"

这些不是错误、不是文件、不是决策、不是 TODO。`user_context` 用固定模板的一句话保存这类事实记录，LLM 兜底提取时严格按模板，不做自由叙述。

---

## 5. 子图职责分界

### 5.1 读写矩阵

| 子图 | 读取结构化状态 | 写入字段 | 写入时机 |
|---|---|---|---|
| **Router**（`intent_classify_node`）| ❌ | `task`, `decisions` | 意图分类完成后 |
| **Chat**（`generate_node`）| ✅ | `knowledge_sources` | RAG 检索完成后 |
| **Diet**（`recommend_node`）| ✅ | `profile`, `knowledge_sources` | 画像提取 + RAG 检索完成后 |
| **Search**（`synthesis_node`）| ✅ | `tool_results_summary.search` | 搜索完成后 |
| **Motion**（API 层）| 部分 | `files` | 图片/视频上传完成后（API 层写入） |
| **MCP**（`execute_tool_node`）| ✅ | `tool_results_summary.mcp` | 工具调用完成后 |

### 5.2 LLM 兜底职责

仅在压缩触发时调用 LLM 提取以下字段（代码规则覆盖不到的语义信息）：
- `todos`：用户说了"等会帮我看下蛋白粉"但当前轮未处理
- `user_context`：用户透露的个人事实

兜底调用使用同一 Qwen3-0.6B，走固定模板 prompt，不做自由推理。

---

## 6. 压缩执行流程

```
每次子图 generate_node 构建 prompt 前：

1. 计算当前 prompt 总长度（系统规则 + 结构化状态 inject + memory + 工具 preview + 用户输入）
2. 如果 ≤ COMPACT_TRIGGER_CHARS → 跳过，正常拼接
3. 如果 > COMPACT_TRIGGER_CHARS：
   a. 保留 memory[-12:]（最近 6 轮原文），其余丢弃
   b. 从丢弃的轮次中，代码规则已写入的字段不动
   c. LLM 兜底扫描丢弃的轮次，提取 todos + user_context，追加到结构化状态
   d. 各字段按 4.2 上限裁剪
   e. 重新拼接 prompt（系统规则 + inject + 6 轮原文 + 工具 preview）
   f. 在对话流生成一条系统消息气泡："📋 对话已浓缩，点击查看摘要"
   g. 气泡展开后展示结构化状态（除 tool_results_summary 完整内容外，显示字段摘要）
```

---

## 7. Prompt 拼接规范

### 7.1 固定顺序（不可变）

```text
[1] # 系统安全规则        ← 从 data/rules/ 加载，永不压缩
[2] # 硬约束（代码注入）    ← 每个子图都有，永不压缩
[3] # 对话摘要             ← 结构化状态注入（可展开）
[4] # 近期对话（最近 6 轮） ← 原文保留
[5] # 工具结果（preview）   ← 限流后的摘要
[6] # 用户问题             ← 本轮输入
```

### 7.2 安全规则的 Pin 机制

**磁盘文件**：`data/rules/safety_rules.md`
- 包含医疗免责声明、使用边界、隐私提示
- 启动时加载一次，缓存为常量
- 每次构建 prompt 时注入到 [1] 位置

**代码注入**：[2] 位置由子图代码根据任务类型注入对应的硬约束：
- Chat: "只基于参考资料回答，不编造健身建议"
- Diet: "画像缺失时提示用户补充，禁止推荐极端饮食"
- Motion: "不替代专业教练做动作诊断"

压缩仅作用于 [3]-[6] 区域，[1][2] 永远不动。

---

## 8. 工具结果分层返回

### 8.1 三段式结构

| 层级 | 内容 | 长度 | 何时展示 |
|---|---|---|---|
| **preview** | 工具名 + 状态 + 简短摘要 | < 500 字符 | 始终在 prompt 里 |
| **full** | 完整 ToolResult.data | 无限制 | 存入临时缓存，用户点击/追问时展开 |
| **index** | 调用 ID + 时间戳 | — | 用于查询 full 结果的 key |

### 8.2 临时缓存

- 存储位置：`_tool_result_cache[user_id]`，和 `_sessions` 同生命周期
- Key：`{execution_id}` 或 `{component}_{timestamp}`
- 淘汰：每个用户最多保留 **20 条**，超出时 FIFO 淘汰

### 8.3 各工具 preview 格式

| 工具 | Preview 格式 |
|---|---|
| Tavily Search | `[搜索] "{query}" → {count} 条结果`（不展示 content 全文） |
| RAG Retrieve | `[知识检索] "{query}" → {count} chunks, 来源: {sources}` |
| MCP get_recipe | `[菜谱] {dish_name} — 配料: {ingredients[:3]}... — 步骤: {n}步` |
| Motion compare | `[动作对比] vs {reference}: DTW={dtw}, cosine={cosine}, shape={shape}` |

---

## 9. 摘要模板（LLM 兜底专用）

仅在压缩触发时调用 LLM 提取，严格按此模板输出，不做自由叙述：

```text
# 对话事实提取（请严格按模板输出，字段缺失写"未记录"）

## 待办事项
- {事项1}
- {事项2}
（没有则写：未记录）

## 用户信息
- {事实1}
- {事实2}
（没有则写：未记录）
```

**关键约束**：
- 只在压缩触发时调用，每次最多一次 LLM 推理
- 温度设 0.0（确定性输出）
- max_new_tokens = 256
- 输出不符合模板 → 丢弃，标记 warning，不影响主流程

---

## 10. 可观测性

### 10.1 系统消息气泡

压缩发生时，在对话流中插入系统消息：

```
📋 对话已浓缩
上一段对话已完成自动总结，点击可查看当前状态。
```

### 10.2 展开内容（结构化展示）

点击展开后展示（前端渲染为结构卡片）：

```text
📌 当前任务
  • diet → mcp：饮食建议后查询菜谱

📁 最近文件
  • squat.mp4（视频，15 帧）→ 对比 squat_standard

⚠️ 最近错误
  • search: NETWORK_ERROR — 已降级为 mock

🧭 路由决策
  • weighted_rules → diet（confidence=0.82）

📝 待办
  • 未记录

👤 用户信息
  • 素食者
  • 训练目标是减脂
```

### 10.3 API 透传

`ChatResponse.execution` 中追加一项：

```json
{
  "component": "memory",
  "mode": "compact",
  "degraded": false,
  "detail": "compressed 8 turns before last 6"
}
```

---

## 11. 多意图路由下的状态共享

### 11.1 状态字段位置

结构化状态放在 `RouterState._structured_state`，不是子图内部状态。

### 11.2 多步执行规则

当 route plan 为 `search → diet` 时：
- `_structured_state` 在子图间**共享**，不清除
- `collect_route_result_node` 不清除 `_structured_state`（区别于当前的 `_retrieved`、`_search_query` 等）
- 第二步（diet）可以看到第一步（search）的 `tool_results_summary.search`

---

## 12. 实现阶段

### Phase 1：数据模型 + 存储
- 在 `RouterState` 中新增 `_structured_state` 字段
- 实现字段上限裁剪逻辑
- 实现工具结果临时缓存 `_tool_result_cache`

### Phase 2：代码规则写入
- Router 节点写入 `task`、`decisions`
- Chat/Diet 节点写入 `knowledge_sources`、`profile`
- Motion API 写入 `files`
- Search/MCP 写入 `tool_results_summary`

### Phase 3：压缩触发 + Prompt 重构
- 实现 token 阈值检查
- 实现压缩流程（保留 6 轮 + LLM 兜底提取）
- 重构所有子图的 prompt 构建节点，统一注入顺序
- 实现安全规则 pin 机制（`data/rules/safety_rules.md`）

### Phase 4：可观测性
- 系统消息气泡（WebSocket 推 `type: "compact"` 事件）
- Web UI + 小程序渲染结构化卡片
- API `execution` 字段追加 compact 标记

### Phase 5：工具结果分层
- Search/MCP/Motion/RAG 实现 preview 格式化
- 完整结果写入临时缓存
- 前端展开查询接口

---

## 13. 风险与边界

| 风险 | 处理 |
|---|---|
| 压缩触发 LLM 调用增加延迟 | 仅压缩时调用一次，温度 0.0，max_tokens=256，预计 <2s |
| 结构化状态字段语义漂移 | 代码规则写入的字段不由 LLM 控制，确保稳定性 |
| 多意图场景下状态被错误清除 | `collect_route_result_node` 显式保留 `_structured_state` |
| 临时缓存无限增长 | 每用户最多 20 条，FIFO 淘汰 |
| 压缩后信息不可逆 | 可在系统消息中提供 `user_id` 和压缩时间戳，便于调试 |

---

## 14. 与现有文档的关系

本文档是上下文压缩与记忆系统的**唯一设计入口**。相关现有文档：
- `docs/README.md` §2、§4 — 当前架构与已知边界
- `docs/interview/04_ONE_PAGE_CHEAT_SHEET.md` — 面试中 Memory 的口径
- `docs/progress/2026-06-27-llm-memory-oom-fix.md` — LLM 内存安全修复记录
- `app/memory/sliding_window.py` — 当前实现源码
- `app/config.py` — memory_max_turns / MAX_PROMPT_CHARS 配置

发生冲突时，本文档优先级仅次于代码本身。
