# Motion API 与面试手册细化记录

## 时间戳

2026-06-23

## 操作类型

功能新增 / 配置变更 / 测试修复 / 文档更新

## 变更概述

本次围绕“面试手册需要更详细，并尽量补齐未实现能力”的要求，完成以下工作：

1. 实现 `/motion/analyze` 独立上传接口。
2. 修正 `app/config.py`，支持通过环境变量覆盖核心配置。
3. 修复 `app/tools/retriever.py` 参数校验分支缺少 `ErrorCode` 导入的问题。
4. 增加 `python-multipart` 依赖，支持 FastAPI 文件上传。
5. 增加 `/motion/analyze` API 测试。
6. 增强测试夹具，mock LLM 和 SentenceTransformer，使测试不依赖本地模型和真实 embedding 包。
7. 将面试手册扩展为带注释代码精读版。

## 代码变更

### `/motion/analyze`

新增接口：

```text
POST /motion/analyze
Content-Type: multipart/form-data
```

请求字段：

- `file`：必填，`.npz` 姿态文件。
- `reference_name`：可选，标准动作名称。

实现逻辑：

- 只接受 `.npz` 文件。
- 将上传文件写入临时文件。
- 复用 `load_npz_pose()` 校验和加载姿态数据。
- 不传 `reference_name` 时返回基础信息：文件名、帧数、关键点数。
- 传入 `reference_name` 时，从 `config.motion_library_dir` 查找标准动作并调用 `compute_similarity()`。
- 请求结束后关闭上传文件并删除临时文件。

### 配置环境变量

`app/config.py` 新增环境变量覆盖能力：

- `MODEL_PATH`
- `MODEL_DEVICE`
- `MODEL_MAX_TOKENS`
- `MODEL_TEMPERATURE`
- `MODEL_TOP_P`
- `MEMORY_MAX_TURNS`
- `RETRIEVER_TOP_K`
- `RETRIEVER_THRESHOLD`
- `EMBEDDING_MODEL`
- `MOTION_LIBRARY_DIR`
- `REACT_MAX_ITERATIONS`
- `MCP_SERVER_COMMAND`
- `API_HOST`
- `API_PORT`

### 测试增强

`tests/conftest.py` 现在会：

- 注入假的 `sentence_transformers` 模块，避免环境未安装该包时 mock 失败。
- mock `LLMLoader.generate()` 和 `generate_stream()`，避免 API 测试加载本地模型。

`tests/test_api.py` 新增：

- 上传内存构造的 `.npz`，验证 `/motion/analyze` 返回 `frames` 和 `joints`。
- 上传非 `.npz`，验证接口返回 422。

## 文档变更

已同步更新：

- `docs/README.md`
  - 更新当前进度。
  - 标记 `/motion/analyze` 已实现。
  - 更新配置环境变量状态。
  - 更新测试结果。

- `docs/API.md`
  - 新增 `/motion/analyze` 接口详细说明。
  - 增加 curl 示例和错误状态说明。

- `docs/interview/PROJECT_INTERVIEW_GUIDE.md`
  - 修正 `/motion/analyze` 完成度描述。
  - 追加“带注释代码精读”章节，覆盖配置、API、Router、RAG、Motion、MCP 和测试夹具。

## 验证结果

已执行：

```bash
python -m py_compile app\config.py app\main.py app\tools\retriever.py tests\test_api.py
python -m pytest tests -q
```

结果：

```text
58 passed, 1 skipped, 1 warning
```

说明：

- `pip install -r requirements.txt` 曾因安装耗时超时，但核心依赖已足够完成本次测试。
- 测试中存在 FastAPI/Starlette TestClient 的 deprecation warning，不影响当前功能。

## Next Steps

1. 准备 `data/motions/` 标准动作 `.npz` 数据。
2. 为 `/motion/analyze` 增加带 `reference_name` 的标准动作对比测试。
3. 验证 Docker 构建流程。
4. 完成微信小程序端到端联调。
