# 2026-07-01 Milvus 真实服务集成测试清单

## 测试目的

这份清单用于在另一台具备 Docker 环境的电脑上验证真实 Milvus RAG 链路。它不是 mock 单元测试，而是验证：

```text
Milvus/etcd/MinIO 容器启动
  -> 后端启用 RETRIEVER_BACKEND=milvus
  -> data/knowledge 文档被分块、向量化并写入 Milvus Collection
  -> 用户问题触发 Milvus vector search
  -> Chat/Diet 子图拿到 chunk、score、source
  -> LLM 或 mock LLM 返回回答
```

## 本机尝试结果

当前这台电脑暂未完成真实服务集成测试，原因是运行环境缺少 Docker CLI 和 `pymilvus`：

```text
docker: 无法将“docker”项识别为 cmdlet
ModuleNotFoundError: No module named 'pymilvus'
```

因此当前已经完成的是：

- `MilvusRetriever` 代码实现。
- fake `pymilvus.MilvusClient` 单元测试。
- Chat/API/Router 主链路回归测试。

尚未完成的是：

- 真实 Milvus 容器启动验证。
- 真实 Collection 创建、写入、搜索验证。
- 真实 Milvus 模式下的 `/chat` 接口验收。

## 前置条件

另一台电脑需要准备：

1. Docker Desktop 已安装并启动。
2. 当前项目代码已拉取到最新分支。
3. Python 环境已安装项目依赖。
4. 如果要跑真实后端，需要可用的 LLM 环境；如果只验证 RAG 链路，可使用 `LLM_MOCK=1`。

安装依赖：

```powershell
pip install -r requirements.txt
```

确认 Docker：

```powershell
docker --version
docker compose version
```

## 测试方式一：只验证 MilvusRetriever 链路

这种方式不启动后端 API，不加载大模型，优先验证 Milvus 写入和检索是否能跑通。

### 1. 启动 Milvus 服务

```powershell
docker compose --profile milvus up -d milvus
```

等待 20-60 秒后检查容器状态：

```powershell
docker compose ps
```

预期至少看到：

```text
milvus
etcd
minio
```

状态为 running 或 healthy。

### 2. 执行 Python 验证脚本

在项目根目录执行：

```powershell
$env:RETRIEVER_BACKEND="milvus"
$env:MILVUS_URI="http://localhost:19530"
$env:MILVUS_COLLECTION="fitness_knowledge_test"
$env:MILVUS_RECREATE_COLLECTION="1"
python -c "from app.tools.retriever import MilvusRetriever; r=MilvusRetriever(uri='http://localhost:19530', collection_name='fitness_knowledge_test', recreate_collection=True); r.add_documents(['减脂期间应保证蛋白质摄入，控制总热量，并优先选择全谷物和蔬菜。'], source='manual_test.txt'); result=r.search('减脂期间蛋白质怎么吃', top_k=3, threshold=0.1); print(result.ok); print(result.meta); print(result.data)"
```

预期结果：

```text
True
{'mode': 'milvus', ...}
[{'content': '减脂期间应保证蛋白质摄入...', 'score': ..., 'source': 'manual_test.txt', ...}]
```

判断标准：

- `result.ok` 为 `True`。
- `result.meta.mode` 为 `milvus`。
- `result.data` 里有 `content`、`score`、`source`。
- `source` 等于 `manual_test.txt`。

如果 `mode` 不是 `milvus`，而是出现 `milvus_fallback`，说明 Milvus 连接、建表、写入或搜索失败，需要查看 `fallback_reason`。

## 测试方式二：验证后端 `/chat` 完整链路

这种方式验证真实 API 链路。建议先用 mock LLM，避免本地大模型加载影响判断。

### 1. 启动 Milvus

```powershell
docker compose --profile milvus up -d milvus
docker compose ps
```

### 2. 启动后端

```powershell
$env:RETRIEVER_BACKEND="milvus"
$env:MILVUS_URI="http://localhost:19530"
$env:MILVUS_COLLECTION="fitness_knowledge"
$env:MILVUS_RECREATE_COLLECTION="1"
$env:LLM_MOCK="1"
$env:MCP_SERVER_COMMAND="mock"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

观察后端日志，预期看到类似信息：

```text
Using Milvus retriever backend
Created Milvus collection: fitness_knowledge
Added xx chunks to Milvus collection fitness_knowledge
Loaded knowledge: fitness_basics.txt
Loaded knowledge: nutrition.txt
```

### 3. 调用 Chat RAG

另开一个 PowerShell：

```powershell
curl.exe -X POST http://127.0.0.1:8000/chat `
  -H "Content-Type: application/json" `
  -d "{\"user_id\":\"milvus-test\",\"message\":\"减脂期间蛋白质应该怎么吃？\"}"
```

预期：

- HTTP 返回 200。
- 返回体包含 `intent` 或路由信息。
- 回答内容与减脂、蛋白质、饮食建议相关。
- 后端日志中有检索 chunk 数量。

### 4. 调用 Diet RAG

```powershell
curl.exe -X POST http://127.0.0.1:8000/chat `
  -H "Content-Type: application/json" `
  -d "{\"user_id\":\"milvus-test\",\"message\":\"我身高170体重80公斤，想减脂，晚餐怎么吃？\"}"
```

预期：

- 路由进入 diet 或相关饮食链路。
- 回答包含用户画像、核心建议、食物推荐或餐次安排。
- 后端不报 Milvus fallback 错误。

## 测试方式三：验证 fallback

停止 Milvus：

```powershell
docker compose --profile milvus stop milvus
```

重新启动后端或继续调用检索。如果 Milvus 不可用，预期：

- 系统不崩溃。
- `MilvusRetriever` fallback 到 `MemoryRetriever`。
- 日志或 `ToolResult.meta` 中能看到 `milvus_fallback` 和 `fallback_reason`。

这个测试证明：即使 Milvus 服务失败，面试演示不会整体断链。

## 常见问题

### 1. docker 命令不存在

表现：

```text
无法将“docker”项识别为 cmdlet
```

处理：

- 安装并启动 Docker Desktop。
- 重启 PowerShell。
- 确认 `docker --version` 可用。

### 2. pymilvus 未安装

表现：

```text
ModuleNotFoundError: No module named 'pymilvus'
```

处理：

```powershell
pip install -r requirements.txt
```

### 3. Milvus 连接失败

表现：

```text
Cannot connect to Milvus at http://localhost:19530
```

处理：

- 确认 `docker compose ps` 中 Milvus 正在运行。
- 本机 Python 连接 Docker 映射端口时使用 `http://localhost:19530`。
- 容器内后端连接 compose 网络时使用 `http://milvus:19530`。

### 4. Collection 维度不匹配

表现：

```text
dimension mismatch
```

处理：

- 确认没有换 embedding 模型后复用旧 Collection。
- 设置：

```powershell
$env:MILVUS_RECREATE_COLLECTION="1"
```

再重启后端。

### 5. 重复数据

当前实现使用 `source + content` 的 hash 作为主键，并优先使用 `upsert`。如果仍发现重复，可设置 `MILVUS_RECREATE_COLLECTION=1` 重建测试 Collection。

## 测试完成后需要记录

如果另一台电脑测试通过，请把以下信息补到本文件或新建测试记录：

```text
测试日期：
测试机器：
Docker 版本：
pymilvus 版本：
Milvus 镜像版本：
测试命令：
Chat RAG 结果：
Diet RAG 结果：
是否出现 fallback：
遗留问题：
```

## 面试口径

可以这样讲：

> 我不是只在代码里写了 Milvus 调用，而是把 RAG 做成 Memory/Milvus 双后端。单元测试验证 Retriever 接口和 fallback，真实集成测试验证 Docker Milvus、Collection 创建、embedding 写入、向量搜索、source 返回和 Chat/Diet 子图调用。默认 Memory 是为了保证演示稳定，Milvus 是可选生产化后端；如果 Milvus 挂了，系统会自动 fallback，不影响主链路。
