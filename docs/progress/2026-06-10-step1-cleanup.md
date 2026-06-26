# Step 1: 代码清理 + Retriever 统一共享

**日期:** 2026-06-10  
**测试结果:** 45 passed, 1 skipped, 0 failed

---

## 做了什么

### 1. 删除死代码

**文件:** `app/graph/router.py`

- 删除了 `stub_subgraph_node` 函数（原第 42-54 行）— 该函数曾用于 Phase 1-6 开发阶段的占位，所有 5 个子图已全部替换为真实实现，不再使用

### 2. 分块正则支持英文

**文件:** `app/tools/retriever.py`

- `_chinese_sentence_split` 函数的分句正则从 `(?<=[。！？\n])` 改为 `(?<=[。！？.!?\n])`
- 添加了英文句号 `.`、感叹号 `!`、问号 `?`，使英文知识库文本也能被正确分块
- 函数 docstring 从"中文 sentence-aware 文本分块"改为中英双语描述

### 3. 共享 Retriever 单例

**新增 (同文件):** `app/tools/retriever.py` 末尾

- `get_shared_retriever()` — 模块级单例，返回全局唯一的 MemoryRetriever 实例
- `load_shared_knowledge_base(docs_dir)` — 从目录加载所有 .txt/.md 文件到共享 retriever

### 4. Chat 子图改用共享 Retriever

**文件:** `app/graph/subgraphs/chat.py`

- 删除了模块级 `_retriever` 单例和 `_get_retriever()` 函数
- 删除了 `load_knowledge_base()` 函数
- `retrieve_node` 现在调用 `get_shared_retriever()`
- 导入从 `from app.tools.retriever import MemoryRetriever` 改为 `from app.tools.retriever import get_shared_retriever`

### 5. Diet 子图改用共享 Retriever

**文件:** `app/graph/subgraphs/diet.py`

- 删除了模块级 `_diet_retriever` 单例和 `_get_diet_retriever()` 函数（该函数自己又加载了一遍知识库）
- `retrieve_nutrition_node` 现在调用 `get_shared_retriever()`
- 导入从 `from app.tools.retriever import MemoryRetriever` 改为 `from app.tools.retriever import get_shared_retriever`

### 6. 路由层统一加载知识库

**文件:** `app/graph/router.py`

- 从导入中移除 `load_knowledge_base`（chat 模块不再导出该函数）
- `build_router_graph()` 中改为调用 `from app.tools.retriever import load_shared_knowledge_base`

---

## 改进效果

| 改动前 | 改动后 |
|--------|--------|
| Diet 和 Chat 各创建独立 MemoryRetriever | 共享同一个 MemoryRetriever 实例 |
| 知识库被嵌入 **2 次**（Chat 一次，Diet 又一次） | 知识库只嵌入 **1 次** |
| 死代码 `stub_subgraph_node` 残留在 router.py | 已清理 |
| 英文知识库分句效果差（正则只匹配中文标点） | 中英文标点都正确匹配 |

---

## 当前测试状态

```
45 passed, 1 skipped (test_llm_loader skip — 模型文件未就绪时正常)
```

## 仍需继续的工作

1. **Step 2:** 实现 `/motion/analyze` 端点 + 独立动作分析能力
2. **Step 3:** 生成模拟 3D 动作 .npz 数据用于测试
3. **后续:** 知识库翻译为中文、MCP Server 真实接入、Milvus 迁移
