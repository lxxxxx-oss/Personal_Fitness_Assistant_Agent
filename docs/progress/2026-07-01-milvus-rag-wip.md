# 2026-07-01 Milvus RAG 接入（WIP）

## 当前状态

操作类型：功能新增 / 配置变更 / 测试补充。

本次工作因会话额度限制暂停，代码以 **WIP（未完成）** 状态提交。Milvus Retriever 的主要代码和协议级单元测试已经加入，但尚未完成 SDK 安装、真实 Milvus 服务联调、全量回归和当前事实文档同步，因此不能把本提交描述为“Milvus RAG 已完整验收”。

## 已完成内容

### Retriever 实现

- 新增 `MilvusRetriever`：
  - 使用 `MilvusClient` 连接配置的 Milvus URI。
  - 创建包含 `id`、`vector`、`content`、`source` 的 Collection Schema。
  - 创建 `IVF_FLAT + COSINE` 向量索引，支持 `nlist`、`nprobe` 配置。
  - 使用稳定内容哈希生成 INT64 主键，通过 upsert 避免同一 chunk 重复入库。
  - 支持向量写入、flush、Top-K 检索、阈值过滤、内容去重、来源返回、Collection 清理和 Client 关闭。
  - 继续使用统一 `ToolResult` / `ErrorCode` 返回结构。
- 新增 `ResilientRetriever`：Milvus 连接或检索失败时，可按配置加载内存 Retriever 并记录 fallback 原因。
- 扩展 `MemoryRetriever`：保存 chunk 来源，`add_documents()` 与 `clear()` 改为返回 `ToolResult`。
- 共享 Retriever 工厂支持 `milvus` / `memory` 后端，并避免同一知识目录在单进程内重复加载。

### 配置与运行入口

- 新增 Milvus URI、token、Collection、索引、`nlist`、`nprobe`、超时和内存降级配置。
- `requirements.txt` 增加 `pymilvus>=2.5.0,<2.6.0`。
- `docker-compose.yml` 增加 etcd、MinIO、Milvus Standalone，并让后端容器显式使用 Milvus。
- Docker Python 基础镜像从 3.13 调整为 3.11，与项目主要运行环境和 PyMilvus 兼容范围保持一致。
- `.gitignore` 增加 Milvus/Docker 数据目录和本地数据库文件忽略项。

## 已修改文件

- `.gitignore`
- `Dockerfile`
- `app/config.py`
- `app/tools/__init__.py`
- `app/tools/retriever.py`
- `docker-compose.yml`
- `requirements.txt`
- `tests/test_milvus_retriever.py`（新增）
- `docs/progress/2026-07-01-milvus-rag-wip.md`（本记录）
- `docs/progress/README.md`

## 工具契约检查

按照 `check-tool-spec` 五项标准完成初步检查：

| 维度 | 当前结论 |
|---|---|
| 职责 | Milvus Retriever 只管理配置指定的 Collection；内存降级由包装器负责 |
| 输入 | URI、Collection 名、索引参数、query、Top-K、threshold 均有类型或范围校验 |
| 输出 | 继续返回 `ToolResult`，检索结果保持 `content/score/index/source` 结构 |
| 权限 | 仅创建、写入、查询和删除配置指定的 Collection，不执行任意命令或用户指定 Collection |
| 错误 | 区分参数、依赖缺失、网络连接和内部错误，并可配置是否降级内存检索 |

当前结论：**代码契约初步通过，真实服务行为仍需联调验证。**

## 已执行验证

```text
python -m py_compile app/config.py app/tools/retriever.py app/tools/__init__.py
通过

python -m pytest tests/test_retriever.py tests/test_milvus_retriever.py -q -p no:cacheprovider
14 passed

git diff --check
通过
```

新增测试使用 fake Milvus Client，覆盖 Collection/索引创建、幂等 upsert、结构化检索、阈值过滤、维度冲突和内存 fallback；它不能替代真实 Milvus 集成测试。

## 未完成与风险

- 当前 `fitness-agent` 环境尚未安装 `pymilvus`。
- 当前机器检测不到可用 Docker Server，无法启动 Milvus Standalone。
- 尚未针对真实 Milvus 验证 Collection Schema、IVF_FLAT 建索引、upsert、flush 和 search 的 SDK 兼容性。
- 尚未运行全量 pytest、Router eval 和 Docker Compose 配置校验。
- `docs/README.md`、`docs/RUNBOOK.md`、面试材料和其他当前事实文档尚未从“Milvus 规划项”更新为准确的 WIP/已实现口径。
- 尚未增加真实服务健康检查脚本或 Milvus 集成测试标记。
- 远端 WIP 阶段曾将 `RETRIEVER_BACKEND` 默认为 `milvus`；合并后当前默认已调整为 `memory`，显式设置 `RETRIEVER_BACKEND=milvus` 时才启用 Milvus。

## 下一步接续位置

1. 在 `fitness-agent` 环境安装更新后的 `requirements.txt`，确认 PyMilvus 版本可导入。
2. 使用 Docker Desktop/WSL2 启动 `docker-compose.yml` 中的 etcd、MinIO 和 Milvus Standalone。
3. 运行真实入库和查询冒烟测试，核对 Schema、索引参数、搜索结果结构与 row count。
4. 修复真实 SDK 差异后运行全量 pytest 与 Router eval。
5. 增加真实 Milvus 集成测试或脚本，并记录未安装 Docker 时的跳过策略。
6. 完成 `README`、`RUNBOOK`、面试文档和测试记录同步后，再把功能状态改为“已完成”。

## 本轮暂停快照（2026-07-01）

本轮继续补齐了真实 Milvus 联调前的工程准备，但因本机 Docker Engine 尚未可用，按用户要求在此暂停。当前仍属于 **WIP（未完成）**，不能表述为“真实 Milvus RAG 已完成验收”。

### 本轮新增与调整

- `app/tools/retriever.py`：为已存在的 Collection 增加索引存在性检查；缺少向量索引时自动创建 `vector_index`，避免只处理“首次建库”场景。
- `tests/test_milvus_retriever.py`：Fake Milvus Client 补充 `list_indexes()`，覆盖既有 Collection 的索引检查逻辑。
- `scripts/smoke_milvus.py`：新增真实 Milvus 冒烟脚本，使用确定性本地编码器完成建库、写入、检索、来源字段、行数、索引与度量类型校验；默认测试结束后清理 Collection，可用 `--keep` 保留。
- `tests/test_milvus_integration.py`：新增可选真实服务集成测试；仅在设置 `MILVUS_TEST_URI` 时执行，默认跳过，避免没有 Milvus 的开发环境误报失败。
- `pytest.ini`：登记 `integration` 测试标记。
- `fitness-agent` 环境已安装并确认可导入 `pymilvus 2.5.18`，原记录中的“SDK 尚未安装”已不再成立。

### 本轮验证结果

```text
Python 语法检查
通过

Retriever 定向测试
14 passed, 1 skipped

全量 pytest
120 passed, 2 skipped, 1 warning

Router 常规评测
66/66，100%

Router 困难评测
36/36；主意图、次意图与路由计划均为 36/36

Docker Compose 配置解析
配置结构可正常渲染；读取本机 Docker 用户配置时出现权限警告
```

全量测试中的 1 条 warning 来自 Starlette `TestClient` 与 httpx 的兼容性提示，与本轮 Milvus 改动无关。

### 当前阻塞与边界

- Docker Desktop 后台进程已经启动，但 Docker Engine CLI 调用持续无响应；访问命名管道时遇到权限限制。
- 尝试启动 `com.docker.service` 时因当前会话缺少服务管理权限而失败。
- 因此 etcd、MinIO、Milvus Standalone 容器尚未真正启动，本轮没有完成真实服务上的冒烟脚本和集成测试。
- `docs/README.md`、`docs/RUNBOOK.md`、面试材料等全局事实文档尚未同步，功能状态必须继续保持 WIP。

### 当前未提交文件

```text
M  app/tools/retriever.py
M  tests/test_milvus_retriever.py
?? pytest.ini
?? scripts/smoke_milvus.py
?? tests/test_milvus_integration.py
M  docs/progress/2026-07-01-milvus-rag-wip.md
```

### 下次从这里继续

1. 使用具备足够权限的 Docker Desktop 会话确认 Docker Engine 可响应。
2. 启动 `docker-compose.yml` 中的 etcd、MinIO 和 Milvus Standalone，并检查容器健康状态。
3. 运行 `python scripts/smoke_milvus.py`，核对真实 Schema、索引、upsert、flush、search、来源字段与 row count。
4. 设置 `MILVUS_TEST_URI` 后运行真实集成测试，处理可能存在的 PyMilvus SDK 行为差异。
5. 真实链路通过后，再同步 `docs/README.md`、`docs/RUNBOOK.md`、面试材料和测试记录，并决定是否将状态改为“已完成”。
