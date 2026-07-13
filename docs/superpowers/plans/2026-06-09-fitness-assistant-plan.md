# 健身智能助手 Agent — 实施计划

> 归档说明：这是项目启动阶段的任务拆解，复选框不再代表当前完成度。当前状态统一查看 [../../01_项目总览.md](../../01_项目总览.md)。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个基于 LangGraph 的多任务健身智能助手，支持联网搜索、3D 动作分析、饮食推荐、RAG 知识问答，通过 FastAPI 提供服务。

**Architecture:** LangGraph 两级图结构——顶层路由图 (Router) 做关键词意图分类并条件分发到四个子图 (Search/Motion/Diet/Chat)，每个子图是独立的 StateGraph。横切层包括滑动窗口记忆和 MCP 客户端。

**Tech Stack:** Python 3.11, LangGraph, HuggingFace Transformers (Qwen3-0.6B), FastAPI, NumPy, Sentence-Transformers, FastDTW, Milvus (后期)

---

## 文件结构总览

```
fitness-assistant/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI入口, /chat, /motion/analyze等路由
│   ├── config.py                  # 配置: 模型路径、API密钥、记忆容量等
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── router.py              # 顶层路由图: intent_classify→条件分发→finalize
│   │   ├── state.py               # RouterState TypedDict定义
│   │   └── subgraphs/
│   │       ├── __init__.py
│   │       ├── search.py          # Tavily搜索子图 (Query理解→搜索→合成)
│   │       ├── motion.py          # 3D动作分析子图 (ReAct: think→parse→tool→check)
│   │       ├── diet.py            # 饮食推荐子图 (RAG增强)
│   │       └── chat.py            # RAG知识问答子图 (检索→过滤→LLM回答)
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── search_tool.py         # Tavily API封装
│   │   ├── motion_tool.py         # 姿态归一化/关节角度/FastDTW/相似度计算
│   │   ├── mcp_client.py          # MCP协议客户端 (subprocess+stdio JSON-RPC)
│   │   └── retriever.py           # 向量检索抽象层 (内存实现→Milvus实现)
│   ├── memory/
│   │   ├── __init__.py
│   │   └── sliding_window.py      # collections.deque滑动窗口记忆
│   └── llm/
│       ├── __init__.py
│       └── loader.py              # Qwen3-0.6B transformers加载+生成封装
├── data/
│   ├── motions/                   # .npz标准动作库
│   └── knowledge/                 # RAG健身知识文档(.txt/.md)
├── tests/
│   ├── __init__.py
│   ├── test_llm_loader.py
│   ├── test_router.py
│   ├── test_sliding_window.py
│   ├── test_retriever.py
│   ├── test_search_tool.py
│   ├── test_motion_tool.py
│   ├── test_mcp_client.py
│   └── test_api.py
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

---

### Task 1: 项目脚手架与依赖安装

**Files:**
- Create: `requirements.txt`
- Create: `app/__init__.py`
- Create: `app/config.py`

- [ ] **Step 1: 编写 requirements.txt**

```txt
# LLM & Graph
langgraph>=0.2.0
langchain-core>=0.3.0
transformers>=4.51.0
torch>=2.0.0

# API
fastapi>=0.100.0
uvicorn>=0.20.0
pydantic>=2.0.0

# Embedding & Vector
sentence-transformers>=3.0.0
numpy>=1.24.0

# Motion Analysis
fastdtw>=0.3.0
scipy>=1.10.0

# Search
tavily-python>=0.3.0

# MCP Client (后期)
# httpx>=0.27.0

# Dev
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

- [ ] **Step 2: 安装依赖**

```bash
cd D:/Users/Agent/Personal_Fitness_Assistant_Agent
pip install -r requirements.txt
```

- [ ] **Step 3: 创建 app/__init__.py**

```python
# app/__init__.py - 空文件,标记app为Python包
```

- [ ] **Step 4: 创建 app/config.py**

```python
"""全局配置管理."""
import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class Config:
    # LLM
    model_path: str = "D:/Users/Agent/model/models/Qwen/Qwen3-0___6B"
    model_device: str = "cpu"  # "cuda" or "cpu"
    model_max_tokens: int = 1024
    model_temperature: float = 0.6
    model_top_p: float = 0.95

    # Memory
    memory_max_turns: int = 6

    # Retriever
    retriever_top_k: int = 5
    retriever_threshold: float = 0.5
    embedding_model: str = "shibing624/text2vec-base-chinese"

    # Tavily Search
    tavily_api_key: str = field(default_factory=lambda: os.getenv("TAVILY_API_KEY", ""))

    # Motion
    motion_library_dir: str = "data/motions"
    react_max_iterations: int = 5

    # MCP
    mcp_server_command: str = "howtocook-mcp"  # Demo阶段mock,后续替换

    # API
    api_host: str = "127.0.0.1"
    api_port: int = 8000


# 全局单例
config = Config()
```

- [ ] **Step 5: 创建其余空 __init__.py**

```bash
touch app/graph/__init__.py
touch app/graph/subgraphs/__init__.py
touch app/tools/__init__.py
touch app/memory/__init__.py
touch app/llm/__init__.py
touch tests/__init__.py
mkdir -p data/motions data/knowledge
```

- [ ] **Step 6: 验证并提交**

```bash
python -c "from app.config import config; print(f'Model: {config.model_path}, Port: {config.api_port}')"
```

预期输出: `Model: D:/Users/Agent/model/models/Qwen/Qwen3-0___6B, Port: 8000`

---

### Task 2: LLM 加载器 — Qwen3 Transformers 封装

**Files:**
- Create: `app/llm/__init__.py`
- Create: `app/llm/loader.py`
- Create: `tests/test_llm_loader.py`

- [ ] **Step 1: 编写失败测试**

创建 `tests/test_llm_loader.py`:

```python
"""LLM加载器测试."""
import pytest
from app.llm.loader import LLMLoader


class TestLLMLoader:
    def test_loader_initializes_with_config(self):
        from app.config import config
        loader = LLMLoader(
            model_path=config.model_path,
            device="cpu",
            max_tokens=64,
            temperature=0.6,
            top_p=0.95,
        )
        assert loader.model_path == config.model_path
        assert loader.device == "cpu"

    def test_generate_returns_string(self):
        """注意: 此测试需要模型文件存在,在不满足条件时skip."""
        import os
        loader = LLMLoader(model_path="skipped", device="cpu")
        if not os.path.exists(loader.model_path):
            pytest.skip("Model file not available")
        result = loader.generate("你好", max_new_tokens=16)
        assert isinstance(result, str)
        assert len(result) > 0
```

- [ ] **Step 2: 运行测试,确认失败**

```bash
pytest tests/test_llm_loader.py::TestLLMLoader::test_loader_initializes_with_config -v
```

预期: FAIL — module not found

- [ ] **Step 3: 实现 LLMLoader**

创建 `app/llm/loader.py`:

```python
"""Qwen3-0.6B 模型加载与生成封装."""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class LLMLoader:
    """加载本地 Qwen3-0.6B 模型,提供统一的 generate() 接口."""

    def __init__(
        self,
        model_path: str,
        device: str = "cpu",
        max_tokens: int = 1024,
        temperature: float = 0.6,
        top_p: float = 0.95,
    ):
        self.model_path = model_path
        self.device = device
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self._model = None
        self._tokenizer = None

    def _ensure_loaded(self):
        """延迟加载模型(首次调用generate时才加载)."""
        if self._model is not None:
            return
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        logger.info(f"Loading model from {self.model_path} on {self.device}...")
        dtype = torch.bfloat16 if self.device == "cuda" else torch.float32
        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_path, trust_remote_code=True
        )
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_path,
            torch_dtype=dtype,
            trust_remote_code=True,
        ).to(self.device)
        self._model.eval()
        logger.info("Model loaded.")

    def generate(
        self,
        prompt: str,
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
    ) -> str:
        """给定提示词,生成文本回复."""
        self._ensure_loaded()
        max_tokens = max_new_tokens or self.max_tokens
        temp = temperature or self.temperature
        p = top_p or self.top_p

        messages = [{"role": "user", "content": prompt}]
        text = self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self._tokenizer(text, return_tensors="pt").to(self.device)

        with __import__("torch").no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=temp,
                top_p=p,
                do_sample=True,
                pad_token_id=self._tokenizer.pad_token_id
                or self._tokenizer.eos_token_id,
            )

        generated = outputs[0][inputs["input_ids"].shape[1] :]
        result = self._tokenizer.decode(generated, skip_special_tokens=True)
        return result.strip()
```

创建 `app/llm/__init__.py`:

```python
from app.llm.loader import LLMLoader

__all__ = ["LLMLoader"]
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_llm_loader.py::TestLLMLoader::test_loader_initializes_with_config -v
```

预期: PASS

- [ ] **Step 5: 提交**

```bash
git add app/llm/ app/config.py tests/test_llm_loader.py requirements.txt
git commit -m "feat: add Qwen3 LLM loader with config"
```

---

### Task 3: 滑动窗口记忆

**Files:**
- Create: `app/memory/sliding_window.py`
- Create: `app/memory/__init__.py`
- Create: `tests/test_sliding_window.py`

- [ ] **Step 1: 编写测试**

创建 `tests/test_sliding_window.py`:

```python
"""滑动窗口记忆测试."""
from app.memory.sliding_window import SlidingWindowMemory


class TestSlidingWindowMemory:
    def test_add_and_get_all(self):
        mem = SlidingWindowMemory(max_turns=3)
        mem.add({"role": "user", "content": "你好"})
        mem.add({"role": "assistant", "content": "你好！"})
        history = mem.get_all()
        assert len(history) == 2
        assert history[0]["role"] == "user"

    def test_evicts_oldest_when_full(self):
        mem = SlidingWindowMemory(max_turns=2)
        mem.add({"role": "user", "content": "msg1"})
        mem.add({"role": "assistant", "content": "reply1"})
        mem.add({"role": "user", "content": "msg2"})
        mem.add({"role": "assistant", "content": "reply2"})
        history = mem.get_all()
        assert len(history) == 2
        assert history[0]["content"] == "msg2"

    def test_clear(self):
        mem = SlidingWindowMemory(max_turns=5)
        mem.add({"role": "user", "content": "test"})
        mem.clear()
        assert len(mem.get_all()) == 0

    def test_max_turns_zero_means_unlimited(self):
        mem = SlidingWindowMemory(max_turns=0)
        for i in range(50):
            mem.add({"role": "user", "content": f"msg{i}"})
        assert len(mem.get_all()) == 50

    def test_get_last_n(self):
        mem = SlidingWindowMemory(max_turns=10)
        mem.add({"role": "user", "content": "a"})
        mem.add({"role": "assistant", "content": "b"})
        mem.add({"role": "user", "content": "c"})
        recent = mem.get_last_n(2)
        assert len(recent) == 2
        assert recent[0]["content"] == "b"
```

- [ ] **Step 2: 运行测试,确认失败**

```bash
pytest tests/test_sliding_window.py -v
```

预期: FAIL — module not found

- [ ] **Step 3: 实现 SlidingWindowMemory**

创建 `app/memory/sliding_window.py`:

```python
"""滑动窗口记忆系统 — 基于 collections.deque 实现."""
from collections import deque
from typing import Dict, List, Optional


class SlidingWindowMemory:
    """可配置容量的滑动窗口记忆,自动淘汰最旧记录."""

    def __init__(self, max_turns: int = 6):
        """
        Args:
            max_turns: 最大保留轮次(每轮=user+assistant两条消息).
                       设为0表示无限制.
        """
        self.max_turns = max_turns
        self._buffer: deque = deque()

    def add(self, message: Dict[str, str]) -> None:
        """添加一条消息到记忆.
        
        Args:
            message: {"role": "user|assistant", "content": "..."}
        """
        max_messages = self.max_turns * 2 if self.max_turns > 0 else None
        if max_messages and len(self._buffer) >= max_messages:
            self._buffer.popleft()
        self._buffer.append(message)

    def add_turn(self, user_msg: str, assistant_msg: str) -> None:
        """便捷方法:同时添加一轮对话(user + assistant)."""
        self.add({"role": "user", "content": user_msg})
        self.add({"role": "assistant", "content": assistant_msg})

    def get_all(self) -> List[Dict[str, str]]:
        """返回所有记忆中的消息(按时间顺序)."""
        return list(self._buffer)

    def get_last_n(self, n: int) -> List[Dict[str, str]]:
        """返回最近n条消息."""
        return list(self._buffer)[-n:] if n > 0 else []

    def clear(self) -> None:
        """清空全部记忆."""
        self._buffer.clear()

    def __len__(self) -> int:
        return len(self._buffer)
```

创建 `app/memory/__init__.py`:

```python
from app.memory.sliding_window import SlidingWindowMemory

__all__ = ["SlidingWindowMemory"]
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_sliding_window.py -v
```

预期: 5 PASS

- [ ] **Step 5: 提交**

```bash
git add app/memory/ tests/test_sliding_window.py
git commit -m "feat: add sliding window memory module"
```

---

### Task 4: 向量检索器 (内存实现)

**Files:**
- Create: `app/tools/retriever.py`
- Create: `tests/test_retriever.py`

- [ ] **Step 1: 编写测试**

创建 `tests/test_retriever.py`:

```python
"""向量检索器测试."""
import pytest
from app.tools.retriever import MemoryRetriever


class TestMemoryRetriever:
    @pytest.fixture
    def retriever(self):
        return MemoryRetriever(embedding_model="shibing624/text2vec-base-chinese")

    @pytest.fixture
    def sample_docs(self):
        return [
            "深蹲是一种有效的下肢训练动作，主要锻炼股四头肌和臀大肌。",
            "减脂期间应控制碳水摄入，增加蛋白质比例。",
            "硬拉时保持背部挺直，避免腰部受伤。",
        ]

    def test_add_and_search(self, retriever, sample_docs):
        retriever.add_documents(sample_docs)
        results = retriever.search("如何做深蹲", top_k=2)
        assert len(results) >= 1
        # 最相关的结果应该包含"深蹲"相关内容
        assert any("深蹲" in r["content"] for r in results)

    def test_search_returns_scores(self, retriever, sample_docs):
        retriever.add_documents(sample_docs)
        results = retriever.search("减脂饮食", top_k=3)
        for r in results:
            assert "score" in r
            assert "content" in r
            assert 0.0 <= r["score"] <= 1.0

    def test_search_with_threshold(self, retriever, sample_docs):
        retriever.add_documents(sample_docs)
        results = retriever.search("瑜伽冥想", top_k=3, threshold=0.8)
        # 阈值很高,应该返回很少或没有结果
        assert len(results) <= 1

    def test_clear(self, retriever, sample_docs):
        retriever.add_documents(sample_docs)
        retriever.clear()
        results = retriever.search("深蹲", top_k=5)
        assert len(results) == 0

    def test_document_count(self, retriever, sample_docs):
        assert retriever.document_count == 0
        retriever.add_documents(sample_docs)
        assert retriever.document_count == 3
```

- [ ] **Step 2: 运行测试,确认失败**

```bash
pytest tests/test_retriever.py -v
```

预期: FAIL

- [ ] **Step 3: 实现 MemoryRetriever**

创建 `app/tools/retriever.py`:

```python
"""向量检索模块 — Demo阶段使用内存存储,后期替换为Milvus."""
import logging
import re
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class MemoryRetriever:
    """基于内存的向量检索器.
    
    使用 Sentence-Transformer 编码文本,NumPy 存储向量,
    余弦相似度检索 + 阈值过滤 + 去重排序后处理.
    """

    def __init__(
        self,
        embedding_model: str = "shibing624/text2vec-base-chinese",
        device: str = "cpu",
    ):
        self.embedding_model_name = embedding_model
        self.device = device
        self._encoder = None
        self._documents: List[str] = []
        self._embeddings: Optional[np.ndarray] = None

    def _ensure_encoder(self):
        """延迟加载 Sentence-Transformer 编码器."""
        if self._encoder is not None:
            return
        from sentence_transformers import SentenceTransformer

        logger.info(f"Loading embedding model: {self.embedding_model_name}")
        self._encoder = SentenceTransformer(
            self.embedding_model_name, device=self.device
        )

    @property
    def document_count(self) -> int:
        return len(self._documents)

    def add_documents(self, docs: List[str]) -> None:
        """添加文档到检索库(自动分块后编码)."""
        self._ensure_encoder()
        chunks = []
        for doc in docs:
            chunks.extend(_chinese_sentence_split(doc))
        if not chunks:
            return
        new_embeddings = self._encoder.encode(chunks, normalize_embeddings=True)
        self._documents.extend(chunks)
        if self._embeddings is None:
            self._embeddings = new_embeddings
        else:
            self._embeddings = np.vstack([self._embeddings, new_embeddings])
        logger.info(f"Added {len(chunks)} chunks, total: {len(self._documents)}")

    def search(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.3,
    ) -> List[Dict]:
        """检索与query最相关的文档片段.
        
        Returns:
            [{"content": str, "score": float, "index": int}, ...]
            按相似度降序排列.
        """
        self._ensure_encoder()
        if self._embeddings is None or len(self._documents) == 0:
            return []

        query_vec = self._encoder.encode(
            [query], normalize_embeddings=True
        )
        # 余弦相似度 (向量已归一化,点积即余弦)
        scores = np.dot(self._embeddings, query_vec.T).flatten()

        # 阈值过滤 → 索引排序 → 取top_k
        qualified = np.where(scores >= threshold)[0]
        sorted_idx = qualified[np.argsort(scores[qualified])[::-1]]
        top_idx = sorted_idx[:top_k]

        # 去重(基于内容)
        seen = set()
        results = []
        for idx in top_idx:
            content = self._documents[int(idx)]
            normalized = content.strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            results.append({
                "content": content,
                "score": float(scores[int(idx)]),
                "index": int(idx),
            })
        return results

    def clear(self) -> None:
        """清空全部文档和向量."""
        self._documents = []
        self._embeddings = None


def _chinese_sentence_split(text: str, max_chunk_chars: int = 500) -> List[str]:
    """中文 sentence-aware 文本分块.
    
    按句号、问号、换行等天然边界切分,长句按最大字符数再切.
    """
    sentences = re.split(r"(?<=[。！？\n])\s*", text)
    chunks = []
    current = ""
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if len(current) + len(sent) <= max_chunk_chars:
            current += sent
        else:
            if current:
                chunks.append(current)
            current = sent
    if current:
        chunks.append(current)
    return chunks or [text]
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_retriever.py -v
```

预期: 5 PASS (首次运行会下载 embedding 模型,可能需要几分钟)

- [ ] **Step 5: 提交**

```bash
git add app/tools/retriever.py tests/test_retriever.py
git commit -m "feat: add memory-based vector retriever with sentence-aware chunking"
```

---

### Task 5: LangGraph 路由层

**Files:**
- Create: `app/graph/state.py`
- Create: `app/graph/router.py`
- Create: `tests/test_router.py`

- [ ] **Step 1: 创建全局状态定义**

创建 `app/graph/state.py`:

```python
"""LangGraph 全局状态定义."""
from typing import Annotated, Dict, List, Optional, TypedDict


class RouterState(TypedDict):
    """路由层全局状态,所有子图共享此结构."""
    user_input: str
    user_id: str
    intent: str  # "search" | "motion" | "diet" | "chat" | "mcp"
    memory: List[Dict[str, str]]
    result: str
    error: Optional[str]
```

- [ ] **Step 2: 编写路由层测试**

创建 `tests/test_router.py`:

```python
"""路由层测试."""
import pytest
from app.graph.state import RouterState
from app.graph.router import (
    classify_intent,
    route_to_subgraph,
    build_router_graph,
)


class TestIntentClassification:
    def test_search_keywords(self):
        assert classify_intent("帮我搜索最新的健身资讯") == "search"
        assert classify_intent("查一下深蹲的标准动作") == "search"

    def test_motion_keywords(self):
        assert classify_intent("分析我的深蹲姿势") == "motion"
        assert classify_intent("帮我看看这个硬拉动作") == "motion"
        assert classify_intent("分析这个.npz文件") == "motion"

    def test_diet_keywords(self):
        assert classify_intent("减脂期间吃什么") == "diet"
        assert classify_intent("给我一份增肌食谱") == "diet"
        assert classify_intent("健身营养怎么搭配") == "diet"

    def test_mcp_keywords(self):
        assert classify_intent("怎么做番茄炒蛋") == "mcp"
        assert classify_intent("菜谱:红烧肉") == "mcp"

    def test_default_to_chat(self):
        assert classify_intent("如何做一个标准的深蹲") == "chat"
        assert classify_intent("今天天气怎么样") == "chat"
        assert classify_intent("你好") == "chat"


class TestRouterGraph:
    def test_build_graph_returns_compiled_graph(self):
        graph = build_router_graph()
        assert graph is not None
        # 验证图可以被invoke
        state: RouterState = {
            "user_input": "你好",
            "user_id": "test_001",
            "intent": "",
            "memory": [],
            "result": "",
            "error": None,
        }
        result = graph.invoke(state)
        assert "result" in result
        assert result["intent"] == "chat"
```

- [ ] **Step 3: 运行测试,确认失败**

```bash
pytest tests/test_router.py -v
```

- [ ] **Step 4: 实现路由层**

创建 `app/graph/router.py`:

```python
"""顶层路由图 — 意图识别 + 条件分发."""
import logging
from typing import Literal

from langgraph.graph import StateGraph, END

from app.graph.state import RouterState

logger = logging.getLogger(__name__)

# 关键词→意图映射
INTENT_RULES = [
    ({"search", "motion", "diet", "mcp"}, None),  # 占位,实际由下面规则覆盖
]

KEYWORD_MAP = {
    "search": ["搜索", "查一下", "最新", "新闻", "热点"],
    "motion": ["动作", "深蹲", "硬拉", "姿势", "分析", ".npz", "卧推", "划船"],
    "diet": ["吃什么", "食谱", "营养", "饮食", "减脂", "增肌", "热量", "蛋白质", "碳水"],
    "mcp": ["怎么做", "菜谱", "烹饪", "做法", "步骤"],
}


def classify_intent(user_input: str) -> str:
    """基于关键词规则进行意图分类."""
    text = user_input.strip()
    for intent, keywords in KEYWORD_MAP.items():
        for kw in keywords:
            if kw in text:
                return intent
    return "chat"  # 默认走RAG问答


def intent_classify_node(state: RouterState) -> RouterState:
    """路由节点: 设置 intent."""
    intent = classify_intent(state["user_input"])
    state["intent"] = intent
    logger.info(f"Intent: {intent} for input: {state['user_input'][:50]}")
    return state


def stub_subgraph_node(state: RouterState) -> RouterState:
    """占位子图节点 — 后续任务会替换为真实子图."""
    intent = state["intent"]
    user_input = state["user_input"]
    # 占位回复
    messages = {
        "search": f"[Search] 正在联网搜索: {user_input}",
        "motion": f"[Motion] 正在分析动作: {user_input}",
        "diet": f"[Diet] 正在生成饮食建议: {user_input}",
        "chat": f"[Chat] 回答: {user_input}",
        "mcp": f"[MCP] 正在查询菜谱: {user_input}",
    }
    state["result"] = messages.get(intent, messages["chat"])
    return state


def route_to_subgraph(state: RouterState) -> Literal["search", "motion", "diet", "chat", "mcp"]:
    """条件边: 根据 intent 路由到对应子图节点."""
    return state["intent"]


def finalize_node(state: RouterState) -> RouterState:
    """最终节点: 确保结果有效,记录日志."""
    if state.get("error"):
        state["result"] = f"处理出错: {state['error']}"
    return state


def build_router_graph():
    """构建顶层路由图.
    
    节点: intent_classify → [search/motion/diet/chat/mcp] → finalize → END
    """
    builder = StateGraph(RouterState)

    # 添加节点
    builder.add_node("intent_classify", intent_classify_node)
    builder.add_node("search", stub_subgraph_node)
    builder.add_node("motion", stub_subgraph_node)
    builder.add_node("diet", stub_subgraph_node)
    builder.add_node("chat", stub_subgraph_node)
    builder.add_node("mcp", stub_subgraph_node)
    builder.add_node("finalize", finalize_node)

    # 设置入口
    builder.set_entry_point("intent_classify")

    # 条件路由: intent_classify → 5个子图节点
    builder.add_conditional_edges(
        "intent_classify",
        route_to_subgraph,
        {
            "search": "search",
            "motion": "motion",
            "diet": "diet",
            "chat": "chat",
            "mcp": "mcp",
        },
    )

    # 所有子图 → finalize → END
    for intent in ["search", "motion", "diet", "chat", "mcp"]:
        builder.add_edge(intent, "finalize")
    builder.add_edge("finalize", END)

    return builder.compile()
```

- [ ] **Step 5: 运行测试**

```bash
pytest tests/test_router.py -v
```

预期: 7 PASS

- [ ] **Step 6: 提交**

```bash
git add app/graph/ tests/test_router.py
git commit -m "feat: add LangGraph router with keyword-based intent classification"
```

---

### Task 6: FastAPI 入口 + 路由骨架集成

**Files:**
- Create: `app/main.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: 编写 API 测试**

创建 `tests/test_api.py`:

```python
"""FastAPI 接口测试."""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestHealthCheck:
    def test_health_returns_200(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestChatEndpoint:
    def test_chat_returns_valid_response(self):
        payload = {
            "user_id": "test_user",
            "message": "如何做深蹲?",
        }
        response = client.post("/chat", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "reply" in data
        assert "intent" in data
        assert isinstance(data["reply"], str)
        assert len(data["reply"]) > 0

    def test_chat_with_empty_message(self):
        response = client.post("/chat", json={
            "user_id": "test_user",
            "message": "",
        })
        assert response.status_code == 422  # validation error

    def test_chat_default_intent_is_chat(self):
        payload = {
            "user_id": "test_user",
            "message": "你好，你是谁？",
        }
        response = client.post("/chat", json=payload)
        data = response.json()
        assert data["intent"] == "chat"


class TestHistoryEndpoint:
    def test_get_history_empty(self):
        response = client.get("/chat/new_user/history")
        assert response.status_code == 200
        data = response.json()
        assert "history" in data
        assert data["history"] == []

    def test_delete_history(self):
        response = client.delete("/chat/new_user/history")
        assert response.status_code == 200
        assert response.json()["status"] == "cleared"
```

- [ ] **Step 2: 运行测试,确认失败**

```bash
pytest tests/test_api.py -v
```

- [ ] **Step 3: 实现 FastAPI 应用**

创建 `app/main.py`:

```python
"""FastAPI 应用入口 — 健身智能助手 API 服务."""
import logging
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.config import config
from app.graph.router import build_router_graph
from app.graph.state import RouterState

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Fitness Assistant API", version="0.1.0")

# 全局路由图实例(启动时编译一次)
_router_graph = None
# 用户会话记忆( Dict[user_id, SlidingWindowMemory] )
_sessions: Dict[str, "SlidingWindowMemory"] = {}


def _get_router_graph():
    global _router_graph
    if _router_graph is None:
        _router_graph = build_router_graph()
    return _router_graph


def _get_or_create_memory(user_id: str):
    from app.memory.sliding_window import SlidingWindowMemory

    if user_id not in _sessions:
        _sessions[user_id] = SlidingWindowMemory(max_turns=config.memory_max_turns)
    return _sessions[user_id]


# --- Request/Response Models ---

class ChatRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    message: str = Field(..., min_length=1, max_length=4096)


class ChatResponse(BaseModel):
    user_id: str
    intent: str
    reply: str
    sources: List[str] = []


class HistoryResponse(BaseModel):
    user_id: str
    history: List[Dict[str, str]]


class ClearResponse(BaseModel):
    user_id: str
    status: str


# --- API Endpoints ---

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """处理用户消息,路由到对应子图,返回回复."""
    memory = _get_or_create_memory(request.user_id)

    state: RouterState = {
        "user_input": request.message,
        "user_id": request.user_id,
        "intent": "",
        "memory": memory.get_all(),
        "result": "",
        "error": None,
    }

    try:
        graph = _get_router_graph()
        result_state = graph.invoke(state)

        reply = result_state.get("result", "")
        intent = result_state.get("intent", "chat")

        # 更新记忆
        memory.add_turn(request.message, reply)

        return ChatResponse(
            user_id=request.user_id,
            intent=intent,
            reply=reply,
        )
    except Exception as e:
        logger.exception(f"Error processing chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat/{user_id}/history", response_model=HistoryResponse)
async def get_history(user_id: str):
    """获取用户对话历史."""
    memory = _get_or_create_memory(user_id)
    return HistoryResponse(
        user_id=user_id,
        history=memory.get_all(),
    )


@app.delete("/chat/{user_id}/history", response_model=ClearResponse)
async def clear_history(user_id: str):
    """清空用户对话历史."""
    memory = _get_or_create_memory(user_id)
    memory.clear()
    return ClearResponse(user_id=user_id, status="cleared")
```

- [ ] **Step 4: 运行 API 测试**

```bash
pytest tests/test_api.py -v
```

预期: 6 PASS

- [ ] **Step 5: 手动验证 API 服务启动**

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
sleep 2
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","message":"你好"}'
```

确认返回包含 `intent: "chat"` 和 `reply` 字段。

- [ ] **Step 6: 提交**

```bash
git add app/main.py tests/test_api.py
git commit -m "feat: add FastAPI entry point with chat endpoint and router integration"
```

---

### Task 7: Chat 子图 — RAG 知识问答（替换占位）

**Files:**
- Create: `app/graph/subgraphs/chat.py`
- Create: `data/knowledge/fitness_basics.txt`
- Modify: `app/graph/router.py` → 替换 chat 的 stub 为真实子图

- [ ] **Step 1: 创建示例健身知识库**

创建 `data/knowledge/fitness_basics.txt`:

```
深蹲(Squat)是最基础的下肢训练动作之一。执行时双脚与肩同宽，背部挺直，下蹲至大腿与地面平行或更低，然后站起。主要训练肌群包括股四头肌、臀大肌和腘绳肌。初学者建议从空杠开始，每组8-12次，做3-4组。

硬拉(Deadlift)是全身性的力量训练动作。双脚与髋同宽，握距略宽于肩，背部保持挺直，通过髋部和膝部同时伸展将杠铃拉起。主要训练下背部、臀部和腿部肌肉。正确的姿势至关重要，弯腰是导致腰部受伤的主要原因。

卧推(Bench Press)是最经典的上肢推类动作。平躺在卧推凳上，双手握住杠铃，从胸部推至手臂伸直。主要训练胸大肌、三角肌前束和肱三头肌。全程保持肩胛骨收紧，下落时杠铃轻触胸部。

减脂的核心原则是热量赤字：每天摄入的热量少于消耗的热量。建议每日热量缺口控制在300-500大卡，配合每周3-5次有氧运动和2-3次力量训练。饮食方面增加蛋白质摄入(每公斤体重1.6-2.2克)，控制碳水化合物和脂肪。

增肌的核心是渐进超负荷(Progressive Overload)：逐步增加训练重量、次数或组数。同时需要保证热量盈余(每日+200-400大卡)和充足蛋白质(每公斤体重1.6-2.2克)。每块肌群每周训练2-3次，每次10-20组。
```

- [ ] **Step 2: 实现 Chat 子图**

创建 `app/graph/subgraphs/chat.py`:

```python
"""Chat 子图 — RAG 知识问答."""
import logging
from typing import Dict, List

from langgraph.graph import StateGraph, END

from app.graph.state import RouterState
from app.tools.retriever import MemoryRetriever

logger = logging.getLogger(__name__)

# 全局检索器实例(模块级单例)
_retriever: MemoryRetriever = None


def _get_retriever() -> MemoryRetriever:
    global _retriever
    if _retriever is None:
        from app.config import config

        _retriever = MemoryRetriever(
            embedding_model=config.embedding_model,
        )
    return _retriever


def load_knowledge_base(docs_dir: str = "data/knowledge"):
    """从指定目录加载所有文本文件到检索器."""
    import os

    retriever = _get_retriever()
    if not os.path.isdir(docs_dir):
        logger.warning(f"Knowledge directory not found: {docs_dir}")
        return
    for fname in os.listdir(docs_dir):
        if fname.endswith((".txt", ".md")):
            fpath = os.path.join(docs_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                text = f.read()
            retriever.add_documents([text])
            logger.info(f"Loaded knowledge: {fname} ({len(text)} chars)")


def retrieve_node(state: RouterState) -> RouterState:
    """检索节点: 从知识库检索相关文档."""
    retriever = _get_retriever()
    results = retriever.search(
        state["user_input"],
        top_k=5,
        threshold=0.3,
    )
    # 将检索结果存入state(通过自定义字段暂存)
    state["_retrieved"] = results  # type: ignore
    logger.info(f"Retrieved {len(results)} chunks for: {state['user_input'][:50]}")
    return state


def generate_node(state: RouterState) -> RouterState:
    """生成节点: 基于检索上下文 + 记忆 + 用户输入,调用LLM生成回答."""
    from app.llm.loader import LLMLoader
    from app.config import config

    # 构建上下文
    retrieved = state.get("_retrieved", [])  # type: ignore
    context_text = ""
    sources = []
    if retrieved:
        for i, r in enumerate(retrieved):
            context_text += f"\n[参考{i+1}] {r['content']}"
            sources.append(r["content"][:80] + "...")

    memory = state.get("memory", [])
    memory_text = ""
    if memory:
        recent = memory[-6:]  # 最近3轮
        memory_text = "\n".join(
            [f"{m['role']}: {m['content']}" for m in recent]
        )

    prompt = f"""你是一个专业的健身助手。请根据以下参考资料回答用户的问题。
如果参考资料不足以回答问题，请如实说明。

## 参考资料
{context_text or "暂无相关参考资料"}

## 对话历史
{memory_text or "无历史对话"}

## 用户问题
{state['user_input']}

请给出专业、准确的回答："""

    llm = LLMLoader(
        model_path=config.model_path,
        device=config.model_device,
        max_tokens=config.model_max_tokens,
        temperature=config.model_temperature,
        top_p=config.model_top_p,
    )
    answer = llm.generate(prompt)
    state["result"] = answer
    state["_sources"] = sources  # type: ignore
    return state


def build_chat_subgraph():
    """构建 Chat RAG 子图: retrieve → generate → END."""
    builder = StateGraph(RouterState)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("generate", generate_node)
    builder.set_entry_point("retrieve")
    builder.add_edge("retrieve", "generate")
    builder.add_edge("generate", END)
    return builder.compile()
```

- [ ] **Step 3: 修改路由层,将 Chat 子图接入**

修改 `app/graph/router.py` 中 `build_router_graph` 的 chat 节点,从 stub 换成真实子图:

在文件顶部添加 import:
```python
from app.graph.subgraphs.chat import build_chat_subgraph, load_knowledge_base
```

在 `build_router_graph` 函数中,替换 `builder.add_node("chat", stub_subgraph_node)` 为:
```python
# 初始化知识库
load_knowledge_base("data/knowledge")
chat_subgraph = build_chat_subgraph()
builder.add_node("chat", chat_subgraph)
```

同时从 `builder.add_node("search", stub_subgraph_node)` 到 `builder.add_node("mcp", stub_subgraph_node)` 的其余三个暂时保留 stub。

- [ ] **Step 4: 运行测试验证**

```bash
pytest tests/test_router.py tests/test_api.py -v
```

- [ ] **Step 5: 提交**

```bash
git add app/graph/subgraphs/chat.py data/knowledge/ app/graph/router.py
git commit -m "feat: add Chat subgraph with RAG knowledge retrieval"
```

---

### Task 8: Search 子图 — Tavily 联网搜索

**Files:**
- Create: `app/tools/search_tool.py`
- Create: `app/graph/subgraphs/search.py`
- Modify: `app/graph/router.py` → 接入 Search 子图

- [ ] **Step 1: 创建 Tavily 搜索工具**

创建 `app/tools/search_tool.py`:

```python
"""Tavily 联网搜索工具封装."""
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class TavilySearchTool:
    """封装 Tavily Search API."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """执行搜索,返回结果列表.
        
        Returns:
            [{"title": str, "url": str, "content": str}, ...]
        """
        if not self.api_key:
            logger.warning("TAVILY_API_KEY not set, using mock search")
            return self._mock_search(query, max_results)

        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=self.api_key)
            response = client.search(query=query, max_results=max_results)
            results = []
            for r in response.get("results", [])[:max_results]:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                })
            return results
        except Exception as e:
            logger.error(f"Tavily search failed: {e}")
            return self._mock_search(query, max_results)

    def _mock_search(self, query: str, max_results: int) -> List[Dict[str, str]]:
        """Mock搜索 — 在没有API Key时返回占位结果."""
        return [
            {
                "title": f"搜索结果: {query}",
                "url": "https://example.com/mock",
                "content": f"这是关于 '{query}' 的模拟搜索结果。配置 TAVILY_API_KEY 以获取真实结果。",
            }
        ]
```

- [ ] **Step 2: 编写 Search 工具测试**

创建 `tests/test_search_tool.py`:

```python
"""Search 工具测试."""
import pytest
from app.tools.search_tool import TavilySearchTool


class TestTavilySearchTool:
    def test_mock_search_without_api_key(self):
        tool = TavilySearchTool(api_key="")
        results = tool.search("深蹲标准动作", max_results=3)
        assert len(results) >= 1
        assert "title" in results[0]
        assert "content" in results[0]
        assert "url" in results[0]

    def test_mock_search_respects_max_results(self):
        tool = TavilySearchTool(api_key="")
        results = tool.search("健身", max_results=1)
        assert len(results) == 1
```

- [ ] **Step 3: 运行测试**

```bash
pytest tests/test_search_tool.py -v
```

- [ ] **Step 4: 实现 Search 子图**

创建 `app/graph/subgraphs/search.py`:

```python
"""Search 子图 — Tavily 联网搜索三阶段链路."""
import logging

from langgraph.graph import StateGraph, END

from app.graph.state import RouterState
from app.tools.search_tool import TavilySearchTool

logger = logging.getLogger(__name__)

_search_tool: TavilySearchTool = None


def _get_tool() -> TavilySearchTool:
    global _search_tool
    if _search_tool is None:
        from app.config import config
        _search_tool = TavilySearchTool(api_key=config.tavily_api_key)
    return _search_tool


def query_understanding_node(state: RouterState) -> RouterState:
    """Query Understanding: LLM改写query,提取搜索关键词."""
    from app.config import config
    from app.llm.loader import LLMLoader

    user_input = state["user_input"]
    prompt = f"""你是一个搜索查询优化专家。请将以下用户问题改写为1-2个简洁的搜索关键词(用空格分隔)。
只输出关键词，不要输出其他内容。

用户问题: {user_input}

搜索关键词:"""

    llm = LLMLoader(
        model_path=config.model_path,
        device=config.model_device,
        max_tokens=64,
        temperature=0.3,
    )
    rewritten = llm.generate(prompt).strip()
    if not rewritten:
        rewritten = user_input
    state["_search_query"] = rewritten  # type: ignore
    logger.info(f"Query rewritten: '{user_input}' → '{rewritten}'")
    return state


def search_node(state: RouterState) -> RouterState:
    """Tavily Search: 执行联网搜索."""
    query = state.get("_search_query", state["user_input"])  # type: ignore
    tool = _get_tool()
    results = tool.search(query, max_results=5)
    state["_search_results"] = results  # type: ignore
    logger.info(f"Search returned {len(results)} results for: {query}")
    return state


def synthesis_node(state: RouterState) -> RouterState:
    """Answer Synthesis: LLM基于搜索结果生成结构化回答."""
    from app.config import config
    from app.llm.loader import LLMLoader

    results = state.get("_search_results", [])  # type: ignore
    sources = []
    result_text = ""
    for i, r in enumerate(results):
        result_text += f"\n[{i+1}] {r['title']}\n{r['content']}\n来源: {r['url']}\n"
        sources.append(r["url"])

    prompt = f"""你是一个专业的健身助手。请基于以下联网搜索结果回答用户的问题。
如果搜索结果不充分，请如实说明并给出通用建议。
回答要结构化，注明信息来源。

## 搜索结果
{result_text}
## 用户问题
{state["user_input"]}

请给出回答:"""

    llm = LLMLoader(
        model_path=config.model_path,
        device=config.model_device,
        max_tokens=config.model_max_tokens,
    )
    answer = llm.generate(prompt)
    state["result"] = answer
    state["_sources"] = sources  # type: ignore
    return state


def build_search_subgraph():
    """构建 Search 子图: query_understanding → search → synthesis → END."""
    builder = StateGraph(RouterState)
    builder.add_node("query_understanding", query_understanding_node)
    builder.add_node("search", search_node)
    builder.add_node("synthesis", synthesis_node)
    builder.set_entry_point("query_understanding")
    builder.add_edge("query_understanding", "search")
    builder.add_edge("search", "synthesis")
    builder.add_edge("synthesis", END)
    return builder.compile()
```

- [ ] **Step 5: 接入路由层**

在 `app/graph/router.py` 中:
```python
from app.graph.subgraphs.search import build_search_subgraph

# 在 build_router_graph 中替换:
builder.add_node("search", build_search_subgraph())
```

- [ ] **Step 6: 运行测试**

```bash
pytest tests/test_router.py tests/test_api.py tests/test_search_tool.py -v
```

- [ ] **Step 7: 提交**

```bash
git add app/tools/search_tool.py app/graph/subgraphs/search.py tests/test_search_tool.py app/graph/router.py
git commit -m "feat: add Search subgraph with Tavily integration"
```

---

### Task 9: Motion 子图 — 3D 动作分析 (ReAct 推理链)

**Files:**
- Create: `app/tools/motion_tool.py`
- Create: `app/graph/subgraphs/motion.py`
- Create: `tests/test_motion_tool.py`

- [ ] **Step 1: 编写姿态分析工具测试**

创建 `tests/test_motion_tool.py`:

```python
"""运动分析工具测试."""
import numpy as np
import pytest
from app.tools.motion_tool import (
    normalize_pose,
    compute_joint_angles,
    compute_similarity,
)


class TestPoseNormalization:
    def test_normalize_centers_pose_at_origin(self):
        # 创建简单3D关键点: (N, 3), 比如髋关节在(1,1,1)
        keypoints = np.array([
            [1.0, 1.0, 1.0],  # hip
            [2.0, 1.0, 1.0],  # shoulder
            [1.0, 2.0, 1.0],  # knee
        ], dtype=np.float32)
        normalized = normalize_pose(keypoints)
        # hip应该在原点附近
        assert abs(normalized[0, 0]) < 1e-5
        assert abs(normalized[0, 1]) < 1e-5
        assert abs(normalized[0, 2]) < 1e-5

    def test_normalize_scales_pose(self):
        keypoints = np.array([
            [0.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],  # 2 units away
        ], dtype=np.float32)
        normalized = normalize_pose(keypoints)
        # 归一化后距离应该是1
        dist = np.linalg.norm(normalized[1] - normalized[0])
        assert abs(dist - 1.0) < 1e-5


class TestJointAngles:
    def test_straight_leg_angle_is_pi(self):
        # 髋(0,0,0) → 膝(0,1,0) → 踝(0,2,0)  直线,角度=π
        hip = np.array([0.0, 0.0, 0.0])
        knee = np.array([0.0, 1.0, 0.0])
        ankle = np.array([0.0, 2.0, 0.0])
        angle = compute_joint_angles(hip, knee, ankle)
        assert np.isclose(angle, np.pi, atol=1e-4)

    def test_right_angle(self):
        # 髋(0,0,0) → 膝(1,0,0) → 踝(1,1,0)  直角 = π/2
        hip = np.array([0.0, 0.0, 0.0])
        knee = np.array([1.0, 0.0, 0.0])
        ankle = np.array([1.0, 1.0, 0.0])
        angle = compute_joint_angles(hip, knee, ankle)
        assert np.isclose(angle, np.pi / 2, atol=1e-4)


class TestSimilarity:
    def test_identical_poses_have_max_similarity(self):
        seq1 = np.random.randn(10, 17, 3).astype(np.float32)
        seq2 = seq1.copy()
        metrics = compute_similarity(seq1, seq2)
        assert metrics["cosine_similarity"] > 0.99
        assert metrics["dtw_distance"] < 0.01
        assert metrics["shape_difference"] < 0.01

    def test_different_poses_have_lower_similarity(self):
        seq1 = np.ones((10, 17, 3), dtype=np.float32)
        seq2 = np.zeros((10, 17, 3), dtype=np.float32)
        metrics = compute_similarity(seq1, seq2)
        assert metrics["cosine_similarity"] < 0.5
```

- [ ] **Step 2: 运行测试,确认失败**

```bash
pytest tests/test_motion_tool.py -v
```

- [ ] **Step 3: 实现姿态分析算法**

创建 `app/tools/motion_tool.py`:

```python
"""3D姿态分析工具 — 归一化、关节角度、FastDTW对齐、相似度计算."""
import logging
from typing import Dict, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def normalize_pose(keypoints: np.ndarray) -> np.ndarray:
    """姿态归一化: 以髋关节(索引0)为中心,缩放到单位尺度.
    
    Args:
        keypoints: (N, 3) 单个帧的关键点数组
    Returns:
        (N, 3) 归一化后的关键点
    """
    center = keypoints[0].copy()  # hip为中心
    centered = keypoints - center
    # 计算尺度因子(所有点到中心的平均距离)
    distances = np.linalg.norm(centered, axis=1)
    scale = np.mean(distances)
    if scale < 1e-8:
        scale = 1.0
    return centered / scale


def compute_joint_angles(
    p1: np.ndarray, p2: np.ndarray, p3: np.ndarray
) -> float:
    """计算三点形成的关节角度: angle(p1-p2-p3).
    
    Args:
        p1, p2, p3: 3D坐标点, p2是关节中心
    Returns:
        弧度值,范围[0, π]
    """
    v1 = p1 - p2
    v2 = p3 - p2
    cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-8)
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    return float(np.arccos(cos_angle))


def load_npz_pose(npz_path: str) -> np.ndarray:
    """加载.npz格式的3D姿态数据.
    
    Args:
        npz_path: .npz文件路径
    Returns:
        (T, J, 3) 数组, T=帧数, J=关键点数, 3=x/y/z
    """
    data = np.load(npz_path)
    # 尝试常见key: 'keypoints', 'pose', 'positions', 或第一个数组
    for key in ["keypoints", "pose", "positions"]:
        if key in data:
            return data[key].astype(np.float32)
    # 取第一个数组
    first_key = list(data.keys())[0]
    return data[first_key].astype(np.float32)


def compute_similarity(
    seq1: np.ndarray,
    seq2: np.ndarray,
) -> Dict[str, float]:
    """计算两个动作序列的多维度相似度.
    
    Args:
        seq1: (T1, J, 3) 第一个动作序列
        seq2: (T2, J, 3) 第二个动作序列
    Returns:
        {"dtw_distance": float, "cosine_similarity": float, "shape_difference": float}
    """
    # 对每帧做归一化
    seq1_norm = np.array([normalize_pose(f) for f in seq1])
    seq2_norm = np.array([normalize_pose(f) for f in seq2])

    # DTW距离
    from scipy.spatial.distance import euclidean
    from fastdtw import fastdtw

    # 展平每帧为向量用于DTW
    flat1 = seq1_norm.reshape(seq1_norm.shape[0], -1)
    flat2 = seq2_norm.reshape(seq2_norm.shape[0], -1)
    dtw_dist, path = fastdtw(flat1, flat2, dist=euclidean)
    # 归一化DTW距离
    max_len = max(len(flat1), len(flat2))
    dtw_normalized = dtw_dist / max_len

    # 余弦相似度(对展平的整体序列向量)
    vec1 = flat1.mean(axis=0)
    vec2 = flat2.mean(axis=0)
    cos_sim = float(
        np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2) + 1e-8)
    )

    # 形状差异 (基于关键点间相对距离的统计差异)
    shape1 = np.array([np.linalg.norm(f - f[0]) for f in seq1_norm])
    shape2 = np.array([np.linalg.norm(f - f[0]) for f in seq2_norm])
    # 插值到相同长度
    if len(shape1) != len(shape2):
        target_len = max(len(shape1), len(shape2))
        shape1_interp = np.interp(
            np.linspace(0, 1, target_len),
            np.linspace(0, 1, len(shape1)),
            shape1,
        )
        shape2_interp = np.interp(
            np.linspace(0, 1, target_len),
            np.linspace(0, 1, len(shape2)),
            shape2,
        )
        shape_diff = float(np.mean(np.abs(shape1_interp - shape2_interp)))
    else:
        shape_diff = float(np.mean(np.abs(shape1 - shape2)))

    return {
        "dtw_distance": round(dtw_normalized, 4),
        "cosine_similarity": round(cos_sim, 4),
        "shape_difference": round(shape_diff, 4),
    }


def list_motion_library(library_dir: str) -> Dict[str, str]:
    """列出动作库中的所有标准动作.
    
    Returns:
        {动作名: .npz文件路径}
    """
    import os

    motions = {}
    if not os.path.isdir(library_dir):
        return motions
    for fname in os.listdir(library_dir):
        if fname.endswith(".npz"):
            name = os.path.splitext(fname)[0]
            motions[name] = os.path.join(library_dir, fname)
    return motions
```

- [ ] **Step 4: 运行工具测试**

```bash
pytest tests/test_motion_tool.py -v
```

- [ ] **Step 5: 实现 Motion 子图 (ReAct 推理链)**

创建 `app/graph/subgraphs/motion.py`:

```python
"""Motion 子图 — 3D动作分析 ReAct 推理链."""
import logging
from typing import Literal

from langgraph.graph import StateGraph, END

from app.graph.state import RouterState

logger = logging.getLogger(__name__)


def think_node(state: RouterState) -> RouterState:
    """Think节点: LLM分析用户意图,决定需要调用哪个工具."""
    from app.config import config
    from app.llm.loader import LLMLoader

    # 检查动作库
    from app.tools.motion_tool import list_motion_library
    library = list_motion_library(config.motion_library_dir)
    lib_names = ", ".join(library.keys()) if library else "无已加载的标准动作"

    prompt = f"""你是一个3D运动分析专家。用户想要分析一个健身动作。
请思考以下问题并给出你的分析计划:
1. 用户想分析什么动作?
2. 需要与标准动作库对比还是独立分析?
3. 应该关注哪些关键技术要点?

已知标准动作库中的动作: {lib_names}

用户输入: {state['user_input']}

请输出你的思考过程和分析计划(用中文):"""

    llm = LLMLoader(
        model_path=config.model_path,
        device=config.model_device,
        max_tokens=512,
        temperature=0.3,
    )
    thought = llm.generate(prompt)
    state["_thought"] = thought  # type: ignore
    state["_iteration"] = state.get("_iteration", 0)  # type: ignore
    logger.info(f"Think complete, thought length: {len(thought)}")
    return state


def parse_node(state: RouterState) -> RouterState:
    """Parse节点: 解析需要调用的工具和参数."""
    from app.tools.motion_tool import list_motion_library
    from app.config import config

    library = list_motion_library(config.motion_library_dir)

    # 解析用户输入中的动作名称
    user_input = state["user_input"]
    tools_to_call = []

    # 检查是否提到了动作库中的动作
    for name, path in library.items():
        if name in user_input:
            tools_to_call.append({"tool": "compare_with_library", "ref_name": name, "ref_path": path})

    # 检查是否提到了.npz文件路径
    if ".npz" in user_input:
        # 提取文件路径
        for word in user_input.split():
            if word.endswith(".npz") or ".npz" in word:
                tools_to_call.append({"tool": "load_user_pose", "file_path": word.strip("，。,.!！")})
                break

    state["_tools_to_call"] = tools_to_call  # type: ignore
    state["_parse_done"] = True  # type: ignore
    return state


def tool_node(state: RouterState) -> RouterState:
    """Tool节点: 执行实际的姿态分析计算."""
    from app.tools.motion_tool import load_npz_pose, compute_similarity

    tools_to_call = state.get("_tools_to_call", [])  # type: ignore
    results = []

    for tool_call in tools_to_call:
        if tool_call["tool"] == "load_user_pose":
            try:
                pose = load_npz_pose(tool_call["file_path"])
                results.append({
                    "type": "load_pose",
                    "file": tool_call["file_path"],
                    "frames": pose.shape[0],
                    "joints": pose.shape[1],
                })
                state["_user_pose"] = pose  # type: ignore
            except Exception as e:
                results.append({"type": "error", "message": str(e)})

        elif tool_call["tool"] == "compare_with_library":
            try:
                ref_pose = load_npz_pose(tool_call["ref_path"])
                user_pose = state.get("_user_pose")  # type: ignore
                if user_pose is not None:
                    metrics = compute_similarity(user_pose, ref_pose)
                    results.append({
                        "type": "comparison",
                        "reference": tool_call["ref_name"],
                        "metrics": metrics,
                    })
            except Exception as e:
                results.append({"type": "error", "message": str(e)})

    state["_tool_results"] = results  # type: ignore
    logger.info(f"Tool execution complete: {len(results)} results")
    return state


def check_node(state: RouterState) -> RouterState:
    """Check节点: 评估结果,决定是否需要继续迭代或可以结束."""
    from app.config import config
    from app.llm.loader import LLMLoader

    iteration = state.get("_iteration", 0)  # type: ignore
    tool_results = state.get("_tool_results", [])  # type: ignore

    # 如果没有工具调用的结果,给出通用分析建议
    if not tool_results:
        prompt = f"""用户想了解: {state['user_input']}
请根据你的健身知识给出动作分析建议。如果用户没有指定具体的.npz文件,
请说明如何准备3D姿态数据(.npz格式),以及系统支持的分析功能。

请给出有帮助的回复:"""
    else:
        # 有实际分析结果
        results_text = ""
        for r in tool_results:
            if r["type"] == "load_pose":
                results_text += f"- 已加载姿态数据: {r['frames']}帧, {r['joints']}个关键点\n"
            elif r["type"] == "comparison":
                m = r["metrics"]
                results_text += f"- 与标准动作'{r['reference']}'对比:\n"
                results_text += f"  DTW距离: {m['dtw_distance']}\n"
                results_text += f"  余弦相似度: {m['cosine_similarity']}\n"
                results_text += f"  形状差异: {m['shape_difference']}\n"
            elif r["type"] == "error":
                results_text += f"- 错误: {r['message']}\n"

        prompt = f"""以下是3D动作分析的结果:
{results_text}

用户问题: {state['user_input']}
思考过程: {state.get('_thought', '')}

请根据以上分析结果,给出对用户动作的评估和建议。用中文回答,语言要专业但易懂。"""

    llm = LLMLoader(
        model_path=config.model_path,
        device=config.model_device,
        max_tokens=config.model_max_tokens,
    )
    answer = llm.generate(prompt)
    state["result"] = answer
    state["_check_pass"] = True  # type: ignore
    return state


def should_continue(state: RouterState) -> Literal["tool", "check"]:
    """决定下一步: 继续执行工具调用还是进入check."""
    tools_to_call = state.get("_tools_to_call", [])  # type: ignore
    iteration = state.get("_iteration", 0)  # type: ignore
    from app.config import config

    if tools_to_call and iteration < config.react_max_iterations:
        state["_iteration"] = iteration + 1  # type: ignore
        return "tool"
    return "check"


def build_motion_subgraph():
    """构建 Motion 子图: think → parse → tool → check → END (ReAct循环)."""
    builder = StateGraph(RouterState)
    builder.add_node("think", think_node)
    builder.add_node("parse", parse_node)
    builder.add_node("tool", tool_node)
    builder.add_node("check", check_node)

    builder.set_entry_point("think")
    builder.add_edge("think", "parse")
    builder.add_conditional_edges(
        "parse",
        should_continue,
        {"tool": "tool", "check": "check"},
    )
    builder.add_edge("tool", "check")
    builder.add_edge("check", END)

    return builder.compile()
```

- [ ] **Step 6: 接入路由层**

修改 `app/graph/router.py`:
```python
from app.graph.subgraphs.motion import build_motion_subgraph

# 替换:
builder.add_node("motion", build_motion_subgraph())
```

- [ ] **Step 7: 运行测试**

```bash
pytest tests/test_motion_tool.py tests/test_router.py -v
```

- [ ] **Step 8: 提交**

```bash
git add app/tools/motion_tool.py app/graph/subgraphs/motion.py tests/test_motion_tool.py app/graph/router.py
git commit -m "feat: add Motion subgraph with ReAct reasoning and 3D pose analysis"
```

---

### Task 10: Diet 子图 — RAG 增强饮食推荐

**Files:**
- Create: `app/graph/subgraphs/diet.py`
- Create: `data/knowledge/nutrition.txt`
- Modify: `app/graph/router.py`

- [ ] **Step 1: 添加营养知识文档**

创建 `data/knowledge/nutrition.txt`:

```
减脂饮食核心原则: 每日热量赤字300-500大卡。宏量营养素配比建议蛋白质40%、碳水30%、脂肪30%。优先选择低GI碳水化合物如燕麦、红薯、糙米。每餐保证20-30克优质蛋白质摄入。每天饮水2-3升。

增肌饮食核心原则: 每日热量盈余200-400大卡。蛋白质摄入量每公斤体重1.6-2.2克。训练后30分钟内补充快吸收蛋白质+碳水(如乳清蛋白+香蕉)。一日5-6餐分散摄入。保证复合碳水化合物占热量的40-50%。

常见健身食物推荐:
高蛋白食物: 鸡胸肉(100g含31g蛋白质)、鸡蛋(每个含6g)、三文鱼(100g含20g)、豆腐(100g含8g)、希腊酸奶(100g含10g)
优质碳水: 燕麦、红薯、糙米、全麦面包、香蕉
健康脂肪: 牛油果、坚果、橄榄油、奇亚籽
训练前餐(训练前1-2小时): 香蕉+全麦面包; 训练后餐(训练后30分钟): 乳清蛋白奶昔+香蕉
```

- [ ] **Step 2: 实现 Diet 子图**

创建 `app/graph/subgraphs/diet.py`:

```python
"""Diet 子图 — RAG 增强饮食推荐."""
import logging

from langgraph.graph import StateGraph, END

from app.graph.state import RouterState
from app.tools.retriever import MemoryRetriever

logger = logging.getLogger(__name__)

_diet_retriever: MemoryRetriever = None


def _get_diet_retriever() -> MemoryRetriever:
    global _diet_retriever
    if _diet_retriever is None:
        from app.config import config

        _diet_retriever = MemoryRetriever(embedding_model=config.embedding_model)
        import os

        docs_dir = "data/knowledge"
        if os.path.isdir(docs_dir):
            for fname in os.listdir(docs_dir):
                if fname.endswith((".txt", ".md")):
                    with open(os.path.join(docs_dir, fname), "r", encoding="utf-8") as f:
                        _diet_retriever.add_documents([f.read()])
    return _diet_retriever


def extract_profile_node(state: RouterState) -> RouterState:
    """提取用户身体参数和目标."""
    from app.config import config
    from app.llm.loader import LLMLoader

    prompt = f"""从用户输入中提取以下信息(如果缺失则标注为"未知"):
- 身高(cm)
- 体重(kg)
- 性别
- 目标(减脂/增肌/维持)
- 饮食偏好(可选)

用户输入: {state['user_input']}

请以JSON格式输出提取结果。"""

    llm = LLMLoader(
        model_path=config.model_path,
        device=config.model_device,
        max_tokens=256,
        temperature=0.2,
    )
    profile_text = llm.generate(prompt)
    state["_user_profile"] = profile_text  # type: ignore
    return state


def retrieve_nutrition_node(state: RouterState) -> RouterState:
    """RAG检索: 从营养知识库检索相关内容."""
    retriever = _get_diet_retriever()
    query = f"{state['user_input']} {state.get('_user_profile', '')}"
    results = retriever.search(query, top_k=5, threshold=0.3)
    state["_retrieved"] = results  # type: ignore
    return state


def recommend_node(state: RouterState) -> RouterState:
    """生成个性化饮食建议."""
    from app.config import config
    from app.llm.loader import LLMLoader

    profile = state.get("_user_profile", "")
    retrieved = state.get("_retrieved", [])  # type: ignore

    context_text = "\n".join([r["content"] for r in retrieved]) if retrieved else ""

    prompt = f"""你是一个专业的健身营养师。请根据以下信息为用户提供个性化的饮食建议。

## 用户信息
{profile}

## 营养知识参考
{context_text}

## 用户问题
{state['user_input']}

请给出具体的饮食建议，包括推荐食物、大致热量范围、餐次安排。用中文回答。"""

    llm = LLMLoader(
        model_path=config.model_path,
        device=config.model_device,
        max_tokens=config.model_max_tokens,
    )
    answer = llm.generate(prompt)
    state["result"] = answer
    return state


def build_diet_subgraph():
    """构建 Diet 子图: extract_profile → retrieve → recommend → END."""
    builder = StateGraph(RouterState)
    builder.add_node("extract_profile", extract_profile_node)
    builder.add_node("retrieve_nutrition", retrieve_nutrition_node)
    builder.add_node("recommend", recommend_node)
    builder.set_entry_point("extract_profile")
    builder.add_edge("extract_profile", "retrieve_nutrition")
    builder.add_edge("retrieve_nutrition", "recommend")
    builder.add_edge("recommend", END)
    return builder.compile()
```

- [ ] **Step 3: 接入路由层**

修改 `app/graph/router.py`:
```python
from app.graph.subgraphs.diet import build_diet_subgraph

# 替换:
builder.add_node("diet", build_diet_subgraph())
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_router.py tests/test_api.py -v
```

- [ ] **Step 5: 提交**

```bash
git add app/graph/subgraphs/diet.py data/knowledge/nutrition.txt app/graph/router.py
git commit -m "feat: add Diet subgraph with RAG-enhanced personalized recommendations"
```

---

### Task 11: MCP 客户端 + MCPTool 子图

**Files:**
- Create: `app/tools/mcp_client.py`
- Create: `app/graph/subgraphs/mcp.py`
- Create: `tests/test_mcp_client.py`

- [ ] **Step 1: 编写 MCP 客户端测试**

创建 `tests/test_mcp_client.py`:

```python
"""MCP 客户端测试."""
import pytest
from app.tools.mcp_client import MCPClient


class TestMCPClient:
    def test_client_initial_state(self):
        client = MCPClient(server_command="echo")
        assert not client.is_connected
        assert client.server_command == "echo"

    def test_client_disconnect_when_not_connected(self):
        client = MCPClient(server_command="echo")
        # 断开未连接的客户端不应报错
        client.disconnect()
        assert not client.is_connected

    def test_format_jsonrpc_request(self):
        client = MCPClient(server_command="echo")
        req = client._build_request("tools/list", {})
        assert req["jsonrpc"] == "2.0"
        assert "id" in req
        assert req["method"] == "tools/list"


class TestMCPMockMode:
    def test_mock_tool_call(self):
        """Mock模式: 返回预设菜谱模板."""
        client = MCPClient(server_command="mock")
        result = client.call_tool("get_recipe", {"dish": "番茄炒蛋"})
        assert result is not None
        assert "番茄" in str(result) or "步骤" in str(result) or "name" in result

    def test_mock_list_tools(self):
        client = MCPClient(server_command="mock")
        tools = client.list_tools()
        assert isinstance(tools, list)
        assert len(tools) >= 1
        assert "name" in tools[0]
```

- [ ] **Step 2: 运行测试,确认失败**

```bash
pytest tests/test_mcp_client.py -v
```

- [ ] **Step 3: 实现 MCP 客户端**

创建 `app/tools/mcp_client.py`:

```python
"""MCP 协议客户端 — subprocess + stdio JSON-RPC."""
import json
import logging
import subprocess
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MCPClient:
    """轻量级 MCP 客户端,通过 subprocess + stdio 与 MCP Server 通信.
    
    Demo阶段: 当server_command为"mock"时使用模拟数据.
    """

    def __init__(self, server_command: str):
        self.server_command = server_command
        self._process: Optional[subprocess.Popen] = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        """启动 MCP Server 子进程,完成 initialize 握手."""
        if self.server_command == "mock":
            self._connected = True
            logger.info("MCP Client in mock mode")
            return True
        try:
            self._process = subprocess.Popen(
                [self.server_command],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            # Initialize 握手
            init_request = self._build_request("initialize", {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "fitness-assistant", "version": "0.1.0"},
            })
            response = self._send_request(init_request)
            self._connected = response is not None
            logger.info(f"MCP connected: {self._connected}")
            return self._connected
        except Exception as e:
            logger.error(f"MCP connect failed: {e}")
            self._connected = False
            return False

    def disconnect(self):
        """终止 MCP Server 子进程."""
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        self._connected = False

    def list_tools(self) -> List[Dict[str, Any]]:
        """获取 MCP Server 提供的工具列表."""
        if self.server_command == "mock":
            return [
                {
                    "name": "get_recipe",
                    "description": "获取菜谱的详细做法和配料",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "dish": {"type": "string", "description": "菜名"}
                        },
                    },
                },
                {
                    "name": "search_ingredients",
                    "description": "根据食材搜索可制作的菜品",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "ingredients": {"type": "string", "description": "食材列表"}
                        },
                    },
                },
            ]

        if not self._connected:
            logger.warning("Not connected, cannot list tools")
            return []

        request = self._build_request("tools/list", {})
        response = self._send_request(request)
        if response and "result" in response:
            return response["result"].get("tools", [])
        return []

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用 MCP Server 的指定工具."""
        if self.server_command == "mock":
            return self._mock_tool_call(tool_name, arguments)

        if not self._connected:
            return {"error": "MCP client not connected"}

        request = self._build_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })
        response = self._send_request(request)
        if response and "result" in response:
            return response["result"]
        return {"error": str(response)}

    def _build_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """构建 JSON-RPC 2.0 请求."""
        return {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }

    def _send_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """发送 JSON-RPC 请求并解析响应."""
        if not self._process or not self._process.stdin:
            return None
        try:
            request_str = json.dumps(request) + "\n"
            self._process.stdin.write(request_str)
            self._process.stdin.flush()
            response_line = self._process.stdout.readline()
            return json.loads(response_line)
        except Exception as e:
            logger.error(f"MCP request failed: {e}")
            return None

    def _mock_tool_call(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Mock工具调用 — 返回预设模板数据."""
        if tool_name == "get_recipe":
            dish = arguments.get("dish", "未知菜品")
            recipes = {
                "番茄炒蛋": {
                    "name": "番茄炒蛋",
                    "ingredients": [
                        "番茄 2个", "鸡蛋 3个", "葱 适量",
                        "盐 适量", "糖 少许", "食用油 适量",
                    ],
                    "steps": [
                        "1. 番茄洗净切小块，鸡蛋打散加少许盐",
                        "2. 热锅加油，倒入蛋液，炒至凝固盛出",
                        "3. 锅中再加少许油，放入番茄块翻炒至出汁",
                        "4. 倒回鸡蛋，加盐和糖调味，撒葱花出锅",
                    ],
                    "tips": "番茄炒软出汁后再加鸡蛋，口感更佳",
                    "calories": "约250大卡/份",
                },
            }
            if dish in recipes:
                return recipes[dish]
            return {
                "name": dish,
                "ingredients": ["详见完整菜谱"],
                "steps": ["请参考具体菜谱获取详细步骤"],
                "tips": "建议查询具体菜谱获取准确做法",
            }

        elif tool_name == "search_ingredients":
            ingredients = arguments.get("ingredients", "")
            return {
                "ingredients": ingredients,
                "suggestions": [
                    {"dish": "番茄炒蛋", "difficulty": "简单", "time": "15分钟"},
                    {"dish": "蛋花汤", "difficulty": "简单", "time": "10分钟"},
                ],
            }

        return {"error": f"Unknown tool: {tool_name}"}
```

- [ ] **Step 4: 实现 MCPTool 子图**

创建 `app/graph/subgraphs/mcp.py`:

```python
"""MCPTool 子图 — MCP 协议工具调用."""
import logging

from langgraph.graph import StateGraph, END

from app.graph.state import RouterState
from app.tools.mcp_client import MCPClient

logger = logging.getLogger(__name__)

_mcp_client: MCPClient = None


def _get_client() -> MCPClient:
    global _mcp_client
    if _mcp_client is None:
        from app.config import config
        _mcp_client = MCPClient(server_command=config.mcp_server_command)
        _mcp_client.connect()
    return _mcp_client


def discover_tools_node(state: RouterState) -> RouterState:
    """发现可用工具."""
    client = _get_client()
    tools = client.list_tools()
    state["_mcp_tools"] = tools  # type: ignore
    logger.info(f"MCP tools available: {[t['name'] for t in tools]}")
    return state


def plan_tool_call_node(state: RouterState) -> RouterState:
    """LLM决定调用哪个MCP工具及参数."""
    from app.config import config
    from app.llm.loader import LLMLoader

    tools = state.get("_mcp_tools", [])  # type: ignore
    tools_desc = "\n".join([f"- {t['name']}: {t.get('description', '')}" for t in tools])

    prompt = f"""你是一个厨房助手。根据用户的问题,从以下可用工具中选择最合适的一个,并提取所需参数。
输出JSON格式: {{"tool": "工具名", "arguments": {{参数}}}}

可用工具:
{tools_desc}

用户问题: {state['user_input']}

JSON:"""

    llm = LLMLoader(
        model_path=config.model_path,
        device=config.model_device,
        max_tokens=256,
        temperature=0.2,
    )
    plan_text = llm.generate(prompt)
    state["_tool_plan"] = plan_text  # type: ignore
    return state


def execute_tool_node(state: RouterState) -> RouterState:
    """执行MCP工具调用."""
    import json

    client = _get_client()
    plan_text = state.get("_tool_plan", "{}")  # type: ignore

    # 尝试解析JSON,提取tool名和arguments
    try:
        # 查找JSON块
        if "{" in plan_text and "}" in plan_text:
            start = plan_text.index("{")
            end = plan_text.rindex("}") + 1
            plan_json = json.loads(plan_text[start:end])
        else:
            plan_json = {}
        tool_name = plan_json.get("tool", "get_recipe")
        arguments = plan_json.get("arguments", {"dish": state["user_input"]})
    except (json.JSONDecodeError, ValueError):
        tool_name = "get_recipe"
        arguments = {"dish": state["user_input"]}

    result = client.call_tool(tool_name, arguments)
    state["_tool_result"] = result  # type: ignore
    return state


def format_result_node(state: RouterState) -> RouterState:
    """格式化MCP工具结果为用户可读的回复."""
    import json

    from app.config import config
    from app.llm.loader import LLMLoader

    result = state.get("_tool_result", {})  # type: ignore

    prompt = f"""请将以下菜谱/工具结果格式化为友好的回复。

工具返回数据: {json.dumps(result, ensure_ascii=False, indent=2)}

用户问题: {state['user_input']}

请用中文给出清晰、实用的回复:"""

    llm = LLMLoader(
        model_path=config.model_path,
        device=config.model_device,
        max_tokens=config.model_max_tokens,
    )
    answer = llm.generate(prompt)
    state["result"] = answer
    return state


def build_mcp_subgraph():
    """构建 MCPTool 子图: discover → plan → execute → format → END."""
    builder = StateGraph(RouterState)
    builder.add_node("discover", discover_tools_node)
    builder.add_node("plan", plan_tool_call_node)
    builder.add_node("execute", execute_tool_node)
    builder.add_node("format", format_result_node)
    builder.set_entry_point("discover")
    builder.add_edge("discover", "plan")
    builder.add_edge("plan", "execute")
    builder.add_edge("execute", "format")
    builder.add_edge("format", END)
    return builder.compile()
```

- [ ] **Step 5: 接入路由层**

修改 `app/graph/router.py`:
```python
from app.graph.subgraphs.mcp import build_mcp_subgraph

# 替换:
builder.add_node("mcp", build_mcp_subgraph())
```

- [ ] **Step 6: 运行测试**

```bash
pytest tests/test_mcp_client.py tests/test_router.py -v
```

- [ ] **Step 7: 提交**

```bash
git add app/tools/mcp_client.py app/graph/subgraphs/mcp.py tests/test_mcp_client.py app/graph/router.py
git commit -m "feat: add MCP client and MCPTool subgraph with mock recipe support"
```

---

### Task 12: 全链路集成测试 + 内存记忆集成

**Files:**
- Modify: `app/main.py` (确认记忆集成)
- Create: `tests/test_integration.py`

- [ ] **Step 1: 创建集成测试**

创建 `tests/test_integration.py`:

```python
"""全链路集成测试."""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestIntegration:
    def test_full_chat_flow_with_memory(self):
        """端到端测试: 多轮对话验证记忆功能."""
        user_id = "integration_test_user"

        # 第一轮: 问健身知识
        resp1 = client.post("/chat", json={
            "user_id": user_id,
            "message": "什么是深蹲?",
        })
        assert resp1.status_code == 200
        assert resp1.json()["intent"] in ["chat", "search"]

        # 第二轮: 追问(需要上下文)
        resp2 = client.post("/chat", json={
            "user_id": user_id,
            "message": "那做深蹲时需要注意什么?",
        })
        assert resp2.status_code == 200
        assert len(resp2.json()["reply"]) > 0

        # 验证记忆
        resp3 = client.get(f"/chat/{user_id}/history")
        assert resp3.status_code == 200
        history = resp3.json()["history"]
        # 应该有4条消息(2轮 * 2)
        assert len(history) >= 2

        # 清空记忆
        resp4 = client.delete(f"/chat/{user_id}/history")
        assert resp4.status_code == 200

        # 验证已清空
        resp5 = client.get(f"/chat/{user_id}/history")
        assert resp5.json()["history"] == []

    def test_intent_routing_diet(self):
        """验证饮食意图路由."""
        resp = client.post("/chat", json={
            "user_id": "test_user",
            "message": "减脂期间应该吃什么?",
        })
        assert resp.status_code == 200
        assert resp.json()["intent"] == "diet"

    def test_intent_routing_motion(self):
        """验证动作分析意图路由."""
        resp = client.post("/chat", json={
            "user_id": "test_user",
            "message": "分析一下我的深蹲姿势",
        })
        assert resp.status_code == 200
        assert resp.json()["intent"] == "motion"

    def test_intent_routing_mcp(self):
        """验证MCP菜谱意图路由."""
        resp = client.post("/chat", json={
            "user_id": "test_user",
            "message": "怎么做番茄炒蛋?",
        })
        assert resp.status_code == 200
        assert resp.json()["intent"] == "mcp"

    def test_intent_routing_search(self):
        """验证搜索意图路由."""
        resp = client.post("/chat", json={
            "user_id": "test_user",
            "message": "搜索一下最新的健身资讯",
        })
        assert resp.status_code == 200
        assert resp.json()["intent"] == "search"

    def test_health_endpoint(self):
        """健康检查."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
```

- [ ] **Step 2: 运行集成测试**

```bash
pytest tests/test_integration.py -v
```

预期: 7 PASS (路由和记忆集成验证)

- [ ] **Step 3: 提交**

```bash
git add tests/test_integration.py
git commit -m "test: add integration tests for full flow and intent routing"
```

---

### Task 13: Docker 化

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

- [ ] **Step 1: 编写 Dockerfile**

```dockerfile
FROM python:3.13-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY app/ ./app/
COPY data/ ./data/

# 模型目录挂载点
RUN mkdir -p /models

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: 编写 docker-compose.yml**

```yaml
version: "3.8"

services:
  fitness-assistant:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - D:/Users/Agent/model/models/Qwen/Qwen3-0___6B:/models/Qwen3-0.6B:ro
    environment:
      - MODEL_PATH=/models/Qwen3-0.6B
      - MODEL_DEVICE=cpu
      - TAVILY_API_KEY=${TAVILY_API_KEY:-}
    restart: unless-stopped
```

- [ ] **Step 3: 构建并验证**

```bash
docker-compose build
docker-compose up -d
sleep 5
curl http://localhost:8000/health
docker-compose down
```

- [ ] **Step 4: 提交**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat: add Dockerfile and docker-compose for containerized deployment"
```

---

### Task 14: 最终验证

- [ ] **Step 1: 运行全部测试**

```bash
pytest tests/ -v
```

目标: 所有测试 PASS.

- [ ] **Step 2: 启动服务并手动验证所有路由**

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
```

测试以下请求:
```bash
# Chat
curl -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" -d '{"user_id":"u1","message":"如何做深蹲?"}'
# Search
curl -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" -d '{"user_id":"u1","message":"搜索最新的健身资讯"}'
# Diet
curl -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" -d '{"user_id":"u1","message":"减脂期间吃什么?"}'
# MCP
curl -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" -d '{"user_id":"u1","message":"怎么做番茄炒蛋?"}'
# Motion
curl -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" -d '{"user_id":"u1","message":"分析深蹲姿势"}'
```

- [ ] **Step 3: 最终提交**

```bash
git add -A
git commit -m "chore: finalize all modules and integration verification"
```
