# 记忆系统设计

> **定位说明**：本文档设计的是持久化记忆系统（存储什么、怎么存、怎么检索、怎么注入）。上下文压缩（`context-compression.md`）是它的下游消费者——压缩层决定 prompt 组装时的取舍策略，记忆系统是压缩层的数据来源。
>
> 记忆系统 ≠ 上下文压缩。记忆系统决定存什么、存多久、怎么检索；上下文压缩决定进 prompt 时带什么、怎么压缩、怎么拼接。

---

## 1. 架构总览

```
                          ┌──────────────────────────┐
                          │     Prompt Builder        │
                          │  (上下文压缩 + 拼接策略)   │
                          └──────────┬───────────────┘
                                     │
          ┌──────────────────────────┼──────────────────────────┐
          │                          │                          │
          ▼                          ▼                          ▼
┌─────────────────┐    ┌───────────────────────┐    ┌──────────────────┐
│SlidingWindowMemory│    │  Memory Retrieval     │    │ compact_summary  │
│ (hot cache)      │    │  SQLite + Milvus      │    │ (active only)    │
│ 最近 6 轮原文     │    │  final_score top-k    │    │ SQLite summaries │
└────────┬────────┘    └───────────┬───────────┘    └────────┬─────────┘
         │                         │                         │
         ▼                         ▼                         ▼
┌──────────────────────────────────────────────────────────────────┐
│                        SQLite (source of truth)                  │
│  conversations │ messages │ memory_items │ summaries │ task_states│
│  memory_sources │ memory_relations │ memory_access_logs          │
│  candidate_memories │ FTS5                                       │
└──────────────────────────────┬───────────────────────────────────┘
                               │ async embedding_jobs
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                        Milvus (embedding retrieval only)          │
│  memory_items embedding                                           │
└──────────────────────────────────────────────────────────────────┘
```

### 1.1 核心原则

- **SQLite 是 source of truth**，不是 Milvus
- **SlidingWindowMemory 只是 hot cache**，服务重启后从 SQLite 恢复
- **写入 SQLite 是主路径**，Milvus 异步同步，写入不阻塞请求链路
- **记忆注入 ≠ 全部注入**，按 final_score 取 top-k，有分层预算控制
- **`_structured_state` 不是长期记忆**，它是当前会话的压缩工作态；只有被 Memory Writer 判定为长期有价值的内容，才抽取进 `memory_items`

---

## 2. 数据模型

### 2.1 核心表：`memory_items`

```sql
CREATE TABLE memory_items (
    id            TEXT PRIMARY KEY,          -- UUID
    user_id       TEXT NOT NULL,             -- 隔离键
    kind          TEXT NOT NULL CHECK (kind IN (
                      'rule','fact','preference','todo',
                      'goal','constraint','decision','note'
                  )),
    content       TEXT NOT NULL,             -- 记忆正文
    importance    REAL NOT NULL DEFAULT 0.5, -- 0.0-1.0，归一化后的重要度
    pinned        INTEGER NOT NULL DEFAULT 0,-- 1 = 永不衰减，始终优先
    scope         TEXT DEFAULT 'global',     -- global / project / conversation
    project_id    TEXT,                      -- 关联项目
    metadata      TEXT DEFAULT '{}',         -- JSON 扩展字段
    access_count  INTEGER DEFAULT 0,         -- 被检索/注入次数
    last_accessed_at TEXT,                   -- ISO timestamp
    created_at    TEXT NOT NULL,
    expires_at    TEXT,                      -- NULL = 永不过期
    status        TEXT NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active','superseded','archived','deleted'))
);

CREATE INDEX idx_memory_user ON memory_items(user_id, status);
CREATE INDEX idx_memory_kind ON memory_items(user_id, kind, status);
CREATE INDEX idx_memory_pinned ON memory_items(user_id, pinned, status);
```

### 2.2 `kind` 枚举语义

| kind | 含义 | 初始 importance | 示例 |
|---|---|---|---|
| `rule` | 项目规则、代码规范、必须遵守的长期规则 | 0.9 | "不能修改 generated 文件" |
| `constraint` | 限制条件、安全边界 | 0.9 | "用户膝盖有旧伤" |
| `goal` | 当前目标 | 0.7 | "训练目标是减脂" |
| `fact` | 稳定事实 | 0.5 | "用户是素食者" |
| `preference` | 用户偏好 | 0.5 | "喜欢详细解释" |
| `decision` | 已做出的设计决策 | 0.6 | "记忆系统选用 SQLite + Milvus" |
| `todo` | 待办事项 | 0.4（按紧急程度浮动） | "完成 memory_items 表设计" |
| `note` | 一般长期笔记、调试经验 | 0.2 | "Qwen3-0.6B 在 CPU 上推理约 X tokens/s" |

`memory_items` 只保存跨会话仍有价值的长期记忆。`compact_summary` 和 `session_summary` 不进入 `memory_items`，统一放在 `summaries` 表中，避免把“当前会话状态快照”和“长期可复用记忆”混在一起。

### 2.3 importance 计算规则

#### 初始值

由 `kind` 决定初始 importance（见上表），pinned 规则的 importance 始终为 1.0。

#### 动态调整

```python
importance = clamp(
    initial_importance
    + 0.10 * min(access_count, 20) / 20  # 频繁引用加权重（最多 +0.1）
    + 0.10 * recency_bonus(last_accessed) # 最近使用加权重
    - 0.02 * weeks_since_creation,        # 时间衰减，按周计算，避免短期记忆过快掉权重
    0.0, 1.0
)
```

- pinned=true 的记忆 **不参与衰减**，importance 保持初始值
- 被 superseded 或 archived 的记忆 **不再注入**
- 如果后续希望更慢衰减，可把 `weeks_since_creation` 换成 `months_since_creation`；不要按天直接衰减，否则常规用户偏好会在短时间内被错误降权。

### 2.4 写入路径

| 来源 | source_type | confidence | 需要确认 |
|---|---|---|---|
| 代码规则自动写入 | `code_rule` | 1.0 | 否 |
| 用户明确说"记住..." | `user_explicit_remember` | 1.0 | 否 |
| LLM 从对话推测 | `llm_candidate` | < 1.0 | **是**（敏感/重要时需用户确认） |
| 压缩流程提取 | `compact_extraction` | 0.7 | 否（非敏感字段） |
| 项目文件导入 | `project_file` | 0.8-1.0 | 否 |
| 人工批量导入 | `manual_import` | 1.0 | 否 |

- 用户明确说"记住..." → **直接写 memory_items**（不走 candidate），`memory_sources.source_type = 'user_explicit_remember'`
- LLM candidate 记忆不直接写入 `memory_items`，先写入 `candidate_memories` 表等待确认，确认后才转为正式记忆

### 2.5 去重策略

#### 主路径：memory_key 优先

每条记忆写入前，先计算 `memory_key = hash(user_id + kind + normalized_content)`。
同 `memory_key` 已存在且 status='active' → 更新已有记录（importance 取 max，access_count + 1），不创建新记录。

#### 辅助路径：embedding 相似度

同 user + 同 kind 但不同 memory_key 时，做 embedding 相似度检查：

| 阈值 | 行为 |
|---|---|
| ≥ **0.95** | **自动合并**：更新已有记录 content，不创建新记录 |
| **0.92-0.95** | **候选去重**：写入 `candidate_memories` 标记 `duplicate_of_memory_id`，不自动合并，等下一次确认 |
| < 0.92 | 视为独立新记忆，正常写入 |

去重在写入时（Python 层）执行，不在 prompt 构建的热路径上。

### 2.6 `_structured_state` 与 `memory_items` 的关系

#### 设计原则

`_structured_state` 和 `memory_items` 不是同一个东西，也不是完全独立：

- **`_structured_state`**（进程内存）：当前会话的压缩工作态，包含 task/files/errors/decisions/todos/tool_results_summary/user_context 等字段。用于当前 conversation 的上下文注入。
- **`memory_items`**（SQLite + Milvus）：长期可检索记忆，只保存跨会话仍有价值的规则、事实、偏好、目标、约束、长期决策、项目知识。
- **关系**：`_structured_state` 是 `memory_items` 的候选来源之一。Memory Writer 判断哪些内容值得长期保存后抽取提升。

#### 字段提升规则

| `_structured_state` 字段 | 提升到 memory_items？| 规则 |
|---|---|---|
| `task` | 当前任务留在 compact_summary。长期目标 → `kind='goal'` | 不全部提升 |
| `files` | 只有稳定项目知识才提升，如 "router.py 是路由入口" → `kind='fact'` | 默认不提升 |
| `errors` | 只有形成可复用调试经验才提升 → `kind='note'` | 默认不提升 |
| `decisions` | 长期架构决策 → `kind='decision'`，同步写入 | 选择性提升 |
| `todos` | 跨会话任务 → `kind='todo'`，其他留在 task_states | 默认不提升 |
| `profile` / `user_context` | 长期偏好/事实/约束 → `kind='preference'/'fact'/'constraint'` | 选择性提升 |
| `knowledge_sources` | 不直接提升，作为 `memory_sources` 的引用证据 | 不提升 |
| `tool_results_summary` | 默认不进 memory_items | 不提升 |

#### 完整数据流

```
当前会话运行
  → 子图写入 _structured_state（进程内临时态）
  → 压缩时持久化落盘 → summaries / task_states（SQLite）
  → Memory Writer 判断长期价值 → 抽取 → memory_items（SQLite + Milvus）
```

### 2.7 辅助表

#### candidate_memories

LLM 从对话推测的候选记忆先入此表，等待用户确认。候选记忆不参与普通检索、FTS5、Milvus embedding 和 prompt 注入。

```sql
CREATE TABLE candidate_memories (
    id                TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL,
    project_id        TEXT,
    conversation_id   TEXT,
    proposed_kind     TEXT NOT NULL,        -- 提议的 kind（同 memory_items.kind 枚举）
    category          TEXT,                 -- 细分类别
    memory_key        TEXT,                 -- 唯一标识键（用于去重）
    content           TEXT NOT NULL,        -- 候选记忆正文
    value_json        TEXT,                 -- JSON 结构化值
    confidence        REAL NOT NULL,        -- LLM 推测可信度（0.0-1.0）
    source_message_id TEXT,                 -- 触发推测的消息 ID
    source_quote      TEXT,                 -- 原文引用
    reason            TEXT,                 -- LLM 推测原因
    sensitivity       TEXT DEFAULT 'normal',-- normal / personal / health / security
    status            TEXT DEFAULT 'pending',-- pending / confirmed / rejected / expired
    duplicate_of_memory_id TEXT,            -- 与已有记忆重复
    conflict_with_memory_id TEXT,           -- 与已有记忆冲突
    confirmed_memory_id TEXT,               -- 确认后生成的 memory_items.id
    created_at        TEXT NOT NULL,
    reviewed_at       TEXT
);
```

**流程**：
1. LLM 从对话中抽取候选记忆 → 写入 `candidate_memories`（status='pending'）
2. 低风险 + 高置信度（如项目事实）→ 可自动确认
3. 敏感内容（用户偏好、个人信息、健康等）→ 需用户确认
4. 用户确认 → 写入 `memory_items` → candidate 标记 `confirmed` + 记录 `confirmed_memory_id`
5. 用户拒绝 → candidate 标记 `rejected`，不进入 memory_items

#### FTS5 全文索引

FTS5 表使用真正独立的虚拟表，不使用 `content_rowid='id'`。原因是 `memory_items.id` 是 TEXT UUID，不能直接和 SQLite FTS5 的整数 `rowid` 对齐。

因此 FTS5 表显式保存 `memory_id UNINDEXED`，全文检索先命中 FTS5，再用 `memory_id` 回查 `memory_items`：

```sql
CREATE VIRTUAL TABLE memory_items_fts USING fts5(
    memory_id UNINDEXED,
    content,
    tokenize='unicode61'
);

-- 触发器：INSERT
CREATE TRIGGER memory_items_fts_insert AFTER INSERT ON memory_items
WHEN NEW.status = 'active'
BEGIN
    INSERT INTO memory_items_fts(memory_id, content)
    VALUES (NEW.id, NEW.content);
END;

-- 触发器：UPDATE
CREATE TRIGGER memory_items_fts_update AFTER UPDATE OF content, status ON memory_items
BEGIN
    DELETE FROM memory_items_fts WHERE memory_id = OLD.id;
    INSERT INTO memory_items_fts(memory_id, content)
    SELECT NEW.id, NEW.content
    WHERE NEW.status = 'active';
END;

-- 触发器：软删除
CREATE TRIGGER memory_items_fts_delete AFTER UPDATE ON memory_items
WHEN OLD.status = 'active' AND NEW.status != 'active'
BEGIN
    DELETE FROM memory_items_fts WHERE memory_id = OLD.id;
END;
```

keyword_score 计算时查询 FTS5：

```sql
SELECT mi.id AS memory_id,
       snippet(memory_items_fts, 1, '<b>', '</b>', '...', 40) AS snippet,
       mi.content,
       mi.kind,
       mi.importance
FROM memory_items_fts
JOIN memory_items mi ON mi.id = memory_items_fts.memory_id
WHERE memory_items_fts MATCH ?
  AND mi.user_id = ?
  AND mi.status = 'active'
ORDER BY rank
LIMIT 20;
```

#### conversations

```sql
CREATE TABLE conversations (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    version       INTEGER NOT NULL DEFAULT 0,  -- 乐观锁版本号
    last_compacted_message_id TEXT,            -- 最近一次被 compact 覆盖到的 message
    status        TEXT NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active','idle','archived','deleted')),
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    last_active_at TEXT NOT NULL,
    idle_timeout_minutes INTEGER DEFAULT 30
);
```

#### messages

```sql
CREATE TABLE messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    user_id         TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('user','assistant','system','compact')),
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    metadata        TEXT DEFAULT '{}'
);

CREATE INDEX idx_messages_conv ON messages(conversation_id, created_at);
```

#### summaries

```sql
CREATE TABLE summaries (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    user_id         TEXT NOT NULL,
    type            TEXT NOT NULL CHECK (type IN ('compact','session')),
    content         TEXT NOT NULL,         -- JSON 结构化摘要内容
    status          TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','superseded','archived')),
    created_at      TEXT NOT NULL
);
```

#### task_states

```sql
CREATE TABLE task_states (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    user_id         TEXT NOT NULL,
    state           TEXT NOT NULL DEFAULT '{}', -- JSON
    updated_at      TEXT NOT NULL
);
```

#### memory_sources

```sql
CREATE TABLE memory_sources (
    id          TEXT PRIMARY KEY,
    memory_id   TEXT NOT NULL REFERENCES memory_items(id),
    source_type TEXT NOT NULL CHECK (source_type IN (
                    'code_rule',
                    'user_explicit_remember',
                    'llm_candidate',
                    'compact_extraction',
                    'project_file',
                    'manual_import'
                )),
    source_ref  TEXT,                   -- 引用：message_id / file_path / rule_path
    confidence  REAL DEFAULT 1.0,
    created_at  TEXT NOT NULL
);
```

#### memory_relations

```sql
CREATE TABLE memory_relations (
    id          TEXT PRIMARY KEY,
    source_id   TEXT NOT NULL REFERENCES memory_items(id),
    target_id   TEXT NOT NULL REFERENCES memory_items(id),
    relation    TEXT NOT NULL,          -- supersedes / contradicts / supports / derives_from
    created_at  TEXT NOT NULL
);
```

#### memory_access_logs

保留策略：**30 天 + 10000 条（MVP）**，后续可扩展至 90 天 + 100000 条。

```sql
CREATE TABLE memory_access_logs (
    id          TEXT PRIMARY KEY,
    memory_id   TEXT NOT NULL REFERENCES memory_items(id),
    user_id     TEXT NOT NULL,
    action      TEXT NOT NULL CHECK (action IN ('retrieved','injected','updated','created','archived')),
    context     TEXT,                   -- 触发上下文（query / conversation_id）
    created_at  TEXT NOT NULL
);

-- MVP 保留策略：30 天 + 每 user 最多 10000 条
-- DELETE FROM memory_access_logs WHERE created_at < datetime('now','-30 days');
-- DELETE FROM memory_access_logs WHERE user_id = ? AND id NOT IN (
--   SELECT id FROM memory_access_logs WHERE user_id = ? ORDER BY created_at DESC LIMIT 10000
-- );
```

#### embedding_jobs

```sql
CREATE TABLE embedding_jobs (
    id          TEXT PRIMARY KEY,
    memory_id   TEXT NOT NULL REFERENCES memory_items(id),
    status      TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','processing','completed','failed')),
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 5,
    next_retry_at TEXT,
    error_msg   TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
```

**重试策略**：指数退避，最多 5 次：

| 重试次数 | 延迟 |
|---|---|
| 1 | 1s |
| 2 | 2s |
| 3 | 4s |
| 4 | 8s |
| 5 | 16s |

```python
next_retry_at = now + min(2 ** (retry_count - 1), 32)  # 秒
```

5 次后仍失败 → `status='failed'`，不再重试，需要人工介入或下次 memory 更新时重新触发。

### 2.8 并发控制

#### conversations 版本号 + Transaction

压缩写入使用 **乐观锁（version 字段）+ SQLite transaction** 双保险：

```
1. 压缩开始前读取 conversation：
   - conversation_id
   - current_version
   - active compact_summary
   - last_compacted_message_id
   - 新增 messages

2. 基于这些内容生成新的 compact_summary

3. 写入时开启 SQLite transaction

4. 更新 conversations 时带版本条件：
   UPDATE conversations
   SET version = version + 1,
       updated_at = ?,
       last_compacted_message_id = ?
   WHERE id = ? AND version = ?   -- 乐观锁检查

5. 如果 affected_rows = 1（无并发冲突）：
   - 将旧 compact_summary 标记为 superseded
   - 插入新的 compact_summary（status='active'）
   - 更新 last_compacted_message_id
   - commit

6. 如果 affected_rows = 0（有并发冲突）：
   - 当前压缩结果丢弃
   - 重新读取最新 state
   - 最多重试 1 次
   - 仍冲突则终止本次压缩，不阻塞请求
```

- **乐观锁**：发现并发冲突——两个压缩流程可能都成功串行提交，但后提交的 summary 基于旧上下文，会覆盖前一个更完整的 summary
- **Transaction**：保证一次压缩写入的多表更新（conversations + summaries + task_states）原子性

---

## 3. 检索与注入

### 3.1 检索流程

每次 builder 构建 prompt 时执行一次 Memory Retrieval：

```
1. 先取 pinned rule + constraint 候选
   SELECT * FROM memory_items
   WHERE user_id = ? AND status = 'active' AND pinned = 1
     AND kind IN ('rule','constraint')
   ORDER BY
     CASE WHEN scope = 'project' AND project_id = ? THEN 0 ELSE 1 END,
     importance DESC,
     last_accessed_at DESC

2. 当前 query 做 hybrid relevance 检索
   - embedding_score: Milvus 向量相似度（COSINE）
   - keyword_score: SQLite FTS5 全文搜索
   - metadata_score: scope / project_id / kind 匹配加分

3. 计算 final_score
   final_score = 0.35 * importance
               + 0.45 * relevance
               + 0.10 * recency
               + 0.10 * pinned_bonus

4. 按分层预算取 top-k 注入 prompt
```

### 3.2 relevance 计算

```python
relevance = 0.6 * embedding_score   # Milvus COSINE (0-1)
          + 0.3 * keyword_score     # FTS5 rank-position 归一化 (0-1)
          + 0.1 * metadata_score    # scope / project_id / kind match (0-1)
```

#### embedding_score

直接使用 Milvus COSINE 相似度，天然 0-1 范围。Milvus 不可用时降级为 0。

#### keyword_score

FTS5 `ORDER BY rank ASC` 取 top-k，Python 层按排名位置归一化，不直接使用 FTS5 raw rank 数值：

```python
# FTS5 返回的排名位置：第 1 名 position=1，第 2 名 position=2，...
keyword_score = 1.0 - (rank_position - 1) / k
# 第 1 名 → 1.0，最后一名 → 1/k
```

#### metadata_score

```python
metadata_score = 0.0
+ (0.4 if scope == 'project' and query_project_id == memory.project_id else 0.0)
+ (0.3 if kind matches query context intent else 0.0)   # 运动类问题优先 kind='fact/preference/goal'
+ (0.3 if category matches query domain else 0.0)        # category='nutrition' 匹配饮食类问题
```

最大值 1.0，无匹配为 0。

### 3.3 final_score 公式

所有因子归一化到 0-1 范围：

| 因子 | 权重 | 归一化方式 | 说明 |
|---|---|---|---|
| `importance` | 0.35 | 直接使用（0.0-1.0） | 从 memory_items.importance 读取 |
| `relevance` | 0.45 | embedding + keyword + metadata 加权 | 见 §3.2 |
| `recency` | 0.10 | `1.0 / (1.0 + weeks_since_last_access)` | 本周访问 → 1.0；约 30 天前 → 0.19 |
| `pinned_bonus` | 0.10 | `0.10 if pinned else 0.0` | pinned 记忆始终获得额外加分 |

### 3.4 注入规则矩阵

| 类型 | 注入规则 |
|---|---|
| `rule` / `constraint`（pinned=true）| **优先注入但不是无限注入**，走自己的子预算（最多 800 tokens）；超出时按 scope / project_id / importance / last_accessed_at 排序，必要时摘要化 |
| `fact` / `preference` / `goal` | 按 `final_score` 取 top-k，共享子预算（最多 700 tokens） |
| `decision` / `todo` / `note` | **不走常驻**，仅当 relevance 命中阈值时注入，共享子预算（最多 500 tokens） |
| compact_summary | 压缩后持续注入当前会话，直到被新 summary 替代，单独预算（800-1200 tokens） |

### 3.5 分层预算模型

```
memory_total_budget = 2000 tokens (硬上限)

子预算（可弹性溢出）：
  pinned rule / constraint    → 最多 800 tokens
  fact / preference / goal    → 最多 700 tokens
  decision / todo / note      → 最多 500 tokens

弹性规则：
  - 某类记忆没用满预算时，剩余额度释放给高 final_score 的其他记忆
  - 超过总预算时，按 final_score 从低到高截断
  - pinned 规则优先进入候选，但仍受 800 tokens 子预算限制
  - pinned 超出预算时，先按 scope / project_id / importance / last_accessed_at 排序；仍超出时生成短摘要，不把全文无限塞进 prompt

排序优先级（同分时）：
  pinned_rule > compact_summary > task_state > 高 final_score 其他记忆
```

### 3.6 compact_summary 生命周期

- **生成**：压缩触发时，输入 = 上一 active compact_summary + 新增 messages + 当前 task_state
- **替换**：新 summary 标记 `active`，旧 summary 标记 `superseded`（保留在 summaries 表用于审计）
- **注入**：仅注入当前 active compact_summary，不注入历史版本
- **不入 memory_items**：compact_summary 是会话状态快照，不是长期记忆；真正长期稳定的规则/偏好/事实/决策才抽取进 memory_items
- **会话结束时**：可生成 session_summary 用于未来恢复会话

---

## 4. 会话生命周期

### 4.1 三者关系

| 组件 | 职责 | 持久化 |
|---|---|---|
| SQLite `conversations` / `messages` | 完整历史，source of truth | ✅ |
| `_sessions` 字典 | 运行时活跃会话对象 | ❌ 进程内存 |
| `SlidingWindowMemory` | 最近 6 轮原文 hot cache | ❌ 进程内存 |

### 4.2 会话创建

- 用户第一次发消息 → 立即创建 `conversations` 记录 + 写入消息
- 前端可传 `conversation_id` 续接旧会话，不传则自动创建新会话

### 4.3 清空历史

- `DELETE /chat/{user_id}/history` → 清空 `SlidingWindowMemory` + archive SQLite 中该 conversation
- 仅清空当前上下文 → 只清空 `SlidingWindowMemory`，不动 SQLite

### 4.4 服务重启恢复

```
1. _sessions 为空（正常）
2. 用户继续某个 conversation_id
   → 从 SQLite messages 读取最近 N 条
   → 恢复 SlidingWindowMemory 最近 6 轮
   → 读取 active compact_summary
   → 读取 task_state
3. 用户不指定 conversation_id
   → 查找该用户最近 active conversation
   → 恢复或新建
```

### 4.5 conversation 状态

| status | 含义 |
|---|---|
| `active` | 当前可继续 |
| `idle` | 超过 `idle_timeout_minutes` 未活跃 |
| `archived` | 用户清空或系统归档 |
| `deleted` | 逻辑删除 |

---

## 5. Milvus 同步策略

### 5.1 异步同步

```
写入 memory_items (SQLite)
  → 创建 embedding_jobs 记录 (status='pending')
  → 后台 worker 读取 pending jobs
  → Sentence-Transformers 编码
  → Milvus upsert（vector_id = memory_id）
  → 更新 embedding_jobs status='completed'
  → 失败时标记 status='failed'，不阻塞记忆写入
```

### 5.2 Milvus Collection Schema

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | VARCHAR (PK) | = memory_items.id |
| `user_id` | VARCHAR | 分区键 |
| `embedding` | FLOAT_VECTOR(768) | text2vec-base-chinese 维度 |
| `kind` | VARCHAR | memory_items.kind |
| `content_hash` | VARCHAR | 去重辅助 |

### 5.3 降级策略

- Milvus 不可用时 → embedding_score 退化为 0，仅用 keyword_score + metadata_score
- embedding_jobs 积压 → 新记忆仍然可被 FTS5 检索到，只是 embedding 检索暂时缺失

---

## 6. API 接口

### 6.1 现有接口改动

**`POST /chat`** 请求体新增字段：

```json
{
  "user_id": "u1",
  "message": "如何做深蹲？",
  "conversation_id": "conv_xxx"   // 可选，不传则自动创建
}
```

**`ChatResponse`** 新增字段：

```json
{
  "conversation_id": "conv_xxx",
  "memory_injected": 5,            // 本次注入了多少条记忆
  "compact_triggered": false       // 本次是否触发了压缩
}
```

### 6.2 新增记忆管理接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/memory?query=xxx&kind=fact&limit=20` | 检索记忆 |
| `POST` | `/memory` | 显式写入一条记忆 |
| `GET` | `/memory/{id}` | 读取单条记忆详情 |
| `PATCH` | `/memory/{id}` | 更新记忆（内容/importance/status） |
| `DELETE` | `/memory/{id}` | 删除/归档记忆 |
| `GET` | `/memory/stats` | 记忆统计（各类型数量/总注入次数等） |
| `GET` | `/memory/candidates` | 查看待确认候选记忆 |
| `POST` | `/memory/candidates/{id}/confirm` | 确认候选记忆 |
| `POST` | `/memory/candidates/{id}/reject` | 拒绝候选记忆 |

---

## 7. 实现阶段

### Phase 1：SQLite 数据层
- 创建 SQLite 数据库文件（`data/memory/memory.db`）
- 建表（所有 10 张表，含 FTS5 虚拟表和触发器）
- 实现 `MemoryStore` 类，封装 CRUD 操作
- 实现 `candidate_memories` 确认/拒绝流程
- 实现内容相似度去重逻辑（memory_key + embedding 辅助）
- 单元测试

### Phase 2：Retrieval 引擎
- 实现 hybrid relevance 计算（embedding + FTS5 rank-position 归一化 + metadata）
- 实现 final_score 排序
- 实现分层预算控制器
- 实现注入规则路由

### Phase 3：Milvus 同步
- 实现 embedding_jobs 后台 worker
- 指数退避重试策略（5 次，1s→2s→4s→8s→16s）
- Milvus Collection 创建
- 降级策略（Milvus 不可用时的 fallback）

### Phase 4：Prompt Builder 集成
- 重构所有子图的 prompt 构建节点
- 统一注入顺序（安全规则 → 硬约束 → compact_summary → 记忆注入 → 最近 6 轮 → 工具 preview → 用户问题）
- 使用 Qwen3 tokenizer 精确执行 budget token 计数
- 与上下文压缩联动

### Phase 5：API 层
- `/chat` 接口新增 `conversation_id` 和响应字段
- `/memory` CRUD 接口 + candidates 确认/拒绝
- 会话生命周期管理

### Phase 6：会话恢复与持久化
- 服务重启恢复逻辑
- 消息历史持久化
- compact_summary 生成与替换（乐观锁 + transaction 并发控制）

---

## 8. 风险与边界

| 风险 | 处理 |
|---|---|
| Milvus 不可用导致检索质量下降 | keyword_score + metadata_score 兜底 |
| embedding_jobs 积压 | 新记忆仍可被 FTS5 检索；worker 可横向扩展；指数退避重试，最多 5 次（1s→2s→4s→8s→16s） |
| 记忆表膨胀 | 按 status 过滤 + 定期清理 archived/deleted + expires_at 自动过期 |
| 重复注入相同记忆 | memory_access_logs 去重 + 连续注入过 N 次的记忆降权 |
| LLM candidate 记忆质量低 | 不入正式表，需用户确认后才激活；敏感内容强制确认 |
| SQLite 并发写入瓶颈 | MVP 阶段单机足够；开启 WAL 模式提升并发读；memory_access_logs 保留 30 天 + 10000 条 |
| 同一用户并发请求 race condition | conversations.version 乐观锁 + 压缩写入 SQLite transaction 保证原子性；冲突时最多重试 1 次 |
| 冷启动无初始记忆 | 首次对话注入空状态；安全规则通过上下文压缩侧做 prompt 前缀注入，不进 memory_items |
| final_score 各因子量级不一致 | importance/relevance/recency 全部归一化到 0-1 范围；pinned_bonus 为固定 0.10 |
| Token 计数偏差 | 使用 Qwen3 tokenizer 精确计数 |
| content 相似记忆重复写入 | 主路径 memory_key 匹配；辅助路径 embedding ≥0.95 自动合并，0.92-0.95 标记候选去重，<0.92 独立新记忆 |

---

## 9. 与现有文档的关系

本文档是记忆系统的**唯一设计入口**。相关现有文档：
- `docs/optimization/context-compression.md` — 上下文压缩设计（记忆系统的下游消费者）
- `docs/README.md` §3、§4 — 当前架构与 Memory 边界
- `docs/interview/04_ONE_PAGE_CHEAT_SHEET.md` — 面试 Memory 口径
- `app/memory/sliding_window.py` — 当前 hot cache 实现
- `app/config.py` — memory_max_turns 配置

发生冲突时，本文档优先级仅次于代码本身。
