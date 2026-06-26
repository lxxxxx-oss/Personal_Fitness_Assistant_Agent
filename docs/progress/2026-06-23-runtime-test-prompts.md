# 运行体验测试语句整理记录

## 时间戳

2026-06-23

## 操作类型

运维验证 / 测试文档新增 / 小修复

## 变更概述

根据“给出测试语句、说明对应功能和正常返回，并再次启动服务”的要求，新增手工体验测试文档：

```text
docs/tests/2026-06-23-manual-test-prompts.md
```

文档覆盖：

- `/health`
- `/ui`
- `/chat`
- `/chat/stream`
- `/motion/analyze`
- history 查询与清空
- Chat/Search/Diet/Motion/MCP 五类意图测试语句
- 异常场景测试

## 代码修复

修复 `app/tools/retriever.py` 中 SentenceTransformer 导入位置：

- 原先 `from sentence_transformers import SentenceTransformer` 在 `try` 外部。
- 如果运行环境没安装 `sentence-transformers`，降级逻辑无法生效。
- 现在将 import 放入 `try` 中，缺包时会正确降级为关键词检索。

## 测试数据

生成了体验用动作文件：

```text
tmp/sample_pose.npz
data/motions/squat.npz
```

用于测试：

- `/motion/analyze` 基础上传分析。
- `/motion/analyze` 携带 `reference_name=squat` 的标准动作对比。

## 服务启动

后端已再次启动到：

```text
http://127.0.0.1:8000
```

说明：

- 当前启动脚本使用 `MCP_SERVER_COMMAND=mock`。
- 如果未配置有效 `MODEL_PATH`，LLM 生成类接口可能返回模型加载错误，但路由和非 LLM 接口可体验。

## Next Steps

1. 配置真实 `MODEL_PATH` 后，重新验证 `/chat` 和 `/chat/stream` 的自然语言回答质量。
2. 用真实动作数据替换临时生成的 `tmp/sample_pose.npz` 和 `data/motions/squat.npz`。
