# 健身智能助手 Agent — 设计规范

**日期:** 2026-06-09  
**状态:** 待评审

---

## 1. 项目概述

基于 LangGraph 图编排框架构建的多任务 LLM 系统，集成了联网搜索、3D 动作分析、饮食推荐与 RAG 知识问答四类功能模块。采用 "路由层 + 执行层" 两级图结构。

## 2. 技术栈

| 组件 | 技术选型 |
|------|----------|
| 图编排框架 | LangGraph |
| LLM | 本地 Qwen3-0.6B (HuggingFace Transformers 加载) |
| 向量数据库 | Demo 阶段: 内存向量存储; 后续: Milvus |
| 嵌入模型 | Sentence-Transformers |
| 协议集成 | 自实现 MCP 客户端 (subprocess + stdio JSON-RPC) |
| API 服务 | FastAPI (为 Android App 做准备) |
| 容器化 | Docker + docker-compose |
| 数值计算 | NumPy |
| 动作分析 | FastDTW, 余弦相似度 |

## 3. 项目结构

```
fitness-assistant/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI 入口
│   ├── config.py                # 配置管理
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── router.py            # 顶层路由图 (StateGraph)
│   │   ├── state.py             # 全局状态定义
│   │   └── subgraphs/
│   │       ├── __init__.py
│   │       ├── search.py        # Tavily 搜索子图
│   │       ├── motion.py        # 3D 动作分析子图
│   │       ├── diet.py          # 饮食推荐子图
│   │       └── chat.py          # RAG 知识问答子图
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── search_tool.py       # Tavily API 封装
│   │   ├── motion_tool.py       # 姿态分析算法
│   │   ├── mcp_client.py        # MCP 协议客户端
│   │   └── retriever.py         # 向量检索（先内存，后 Milvus）
│   ├── memory/
│   │   ├── __init__.py
│   │   └── sliding_window.py    # deque 滑动窗口记忆
│   └── llm/
│       ├── __init__.py
│       └── loader.py            # Qwen3 Transformers 加载器
├── data/
│   ├── motions/                 # .npz 标准动作库
│   └── knowledge/               # RAG 知识文档
├── tests/
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## 4. 路由架构

### 4.1 全局状态 (RouterState)

```python
class RouterState(TypedDict):
    user_input: str           # 用户输入
    user_id: str              # 用户标识
    intent: str               # "search" | "motion" | "diet" | "chat" | "mcp"
    memory: List[Dict]        # 滑动窗口记忆 (最近6轮对话)
    result: str               # 子图执行结果
    error: Optional[str]      # 错误信息
```

### 4.2 意图分流规则

| 关键词 | 路由目标 |
|--------|----------|
| 搜索 / 查一下 / 最新 | Search 子图 |
| 动作 / 深蹲 / 硬拉 / 姿势 / 分析 / .npz | Motion 子图 |
| 吃什么 / 食谱 / 营养 / 饮食 / 减脂 / 增肌 | Diet 子图 |
| 怎么做 / 菜谱 / 烹饪 / 做法 | MCPTool 子图 |
| 其他（默认） | Chat 子图 (RAG) |

### 4.3 两级图结构

路由层 (Router StateGraph) 做两件事：意图识别 + 条件分发。每个子图是独立的 StateGraph，内部有自己的状态，通过 RouterState 共享输入输出。

```
用户输入 → intent_classify → route_to_subgraph → [子图执行] → finalize → 返回结果
```

## 5. 子工作流设计

### 5.1 Search 子图 — Tavily 联网搜索

```
Query Understanding → Tavily Search → Answer Synthesis
```

- **Query Understanding:** LLM 对用户问题进行 query rewrite 与关键词优化
- **Tavily Search:** 调用 Tavily API 实时检索互联网信息
- **Answer Synthesis:** 基于搜索结果生成带来源信息的结构化回答

### 5.2 Motion 子图 — 3D 动作分析 (ReAct 推理链)

```
think → parse → tool → check
  ↑                        ↓ (条件循环, 最大迭代数=N)
  └────────────────────────┘
```

**tool 节点算法链路:**
1. 加载 .npz 3D 人体姿态关键点数据
2. 姿态归一化
3. 关节角度计算
4. FastDTW 时间序列对齐
5. 多维度相似度计算 (DTW 距离, 余弦相似度, 形状差异)

**支持两种分析模式:**
- 标准动作库对比：用户上传动作 .npz → 与标准库中的动作进行相似度匹配
- 独立分析：对单个动作的姿态质量进行评分和反馈

### 5.3 Diet 子图 — RAG 增强饮食推荐

```
用户信息(身高/体重/目标等) → RAG 检索营养知识 → LLM 生成个性化饮食建议
```

- 从健身营养知识库中检索相关内容
- 结合用户身体参数和目标 (减脂/增肌) 生成个性化推荐

### 5.4 Chat 子图 — RAG 知识问答

```
user_input → 向量检索 → 阈值过滤 + 去重 + 排序 → LLM + 检索上下文 → 回答
```

- 中文 sentence-aware 文本分块
- Sentence-Transformer 向量化编码
- Demo 阶段: 内存向量存储 + 余弦相似度检索
- 后续: Milvus IVF_FLAT 索引 + COSINE 检索

### 5.5 MCPTool 子图

- Demo 阶段: Mock 实现，接收菜谱类问题 → 返回预设模板
- 后续: 自实现 MCP 客户端 (subprocess + stdio JSON-RPC) 对接 howtocook-mcp Server

## 6. 横切模块

### 6.1 滑动窗口记忆

- 基于 `collections.deque` 实现，可配置容量
- 默认保存最近 6 轮对话
- 所有子图共享同一个记忆实例
- 支持: 添加、获取、逐条淘汰、清空

### 6.2 LLM 加载器

- 使用 HuggingFace Transformers 加载 Qwen3-0.6B
- 统一封装 `generate(prompt)` 接口，供所有子图调用
- 支持配置: temperature, max_tokens, top_p

## 7. API 接口设计

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/chat` | 发送消息，返回助手回复 |
| GET | `/chat/{user_id}/history` | 获取用户对话历史 |
| DELETE | `/chat/{user_id}/history` | 清空对话历史 |
| POST | `/motion/analyze` | 上传 .npz 动作数据进行分析 |
| GET | `/health` | 健康检查 |

**请求/响应格式:**
```json
// POST /chat
{
  "user_id": "user_001",
  "message": "如何做一个标准的深蹲？"
}
// Response
{
  "intent": "chat",
  "reply": "...",
  "sources": ["来源1", "来源2"]
}
```

## 8. 阶段实施路线图

| 阶段 | 内容 | 交付物 |
|------|------|--------|
| Phase 1 | 项目脚手架 + 基础框架 | 目录结构, config, LLM 加载器, FastAPI 骨架 |
| Phase 2 | 路由骨架 + Chat 子图 | 完整路由图 + 内存 RAG + CLI 可交互 |
| Phase 3 | Search 子图 | Tavily 集成, 三阶段搜索链路 |
| Phase 4 | Motion 子图 | 姿态分析算法, ReAct 推理链 |
| Phase 5 | Diet 子图 | RAG 增强饮食推荐 |
| Phase 6 | MCPTool 子图 | Mock → 真实 MCP Client |
| Phase 7 | 横切能力 | 滑动窗口记忆, 会话管理 |
| Phase 8 | Milvus 替换 | 内存存储 → Milvus 向量数据库 |
| Phase 9 | 集成测试 + Docker 化 | 全链路测试, 容器化部署 |

## 9. 暂不纳入范围

- Android App 前端（后续独立开发，API 已为此设计）
- 用户认证 / 权限系统
- 多语言支持（当前仅中文）
- 模型热切换 / 多模型路由
