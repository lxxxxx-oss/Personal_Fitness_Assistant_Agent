# Codex Session State

## Current Task

- Status: idle
- Goal: 依据模型上下文预算动态计算旧对话摘要触发水位，并统一记忆/上下文压缩的代码、测试和文档口径。
- Updated: 2026-08-17

## Progress

- 已新增 `derive_conversation_summary_trigger()`：默认按主动 compact Token 线的 35% 派生摘要水位，并限制在 900—4000 Token。
- 默认字符水位改为摘要 Token 水位的 4 倍；显式正数配置仍可覆盖自动结果。
- 摘要检查结果会返回实际 Token/字符阈值，便于执行轨迹和排错。
- 已核对同范围既有口径：Prompt 轮询装箱、安全内容固定保留、超长条目跳过后继续其他队列、摘要失败退回最近窗口均已有代码。
- SQLite 完整历史保留上限仍按此前决定作为未来优化，本轮未扩展。
- 代码事实、运行配置、项目证据、学习材料和模拟面试记录已同步。

## Touched Files

- `docs/interview/05_三大核心亮点模拟面试实录.md`
- `app/config.py`
- `app/llm/context_window.py`
- `app/memory/conversation_summary.py`
- `tests/test_config.py`
- `tests/test_context_window.py`
- `tests/test_conversation_summary.py`
- `docs/project/项目总览.md`
- `docs/project/运行与排错.md`
- `docs/project/项目证据.md`
- `docs/project/optimization/上下文压缩设计.md`
- `docs/learning/03_简历技术点总表.md`
- `docs/learning/09_简历项目描述与防守边界.md`
- `docs/learning/10_记忆与上下文专项追问.md`
- `docs/interview/03_分层记忆与上下文压缩专项面试问答.md`
- `.codex/SESSION_STATE.md`

## Key Decisions

- 摘要属于跨请求持久化维护，阈值在服务启动时由稳定配置派生，不随单次请求模型选择来回抖动。
- 35%、900 和 4000 是可配置的工程起点，不包装成线上评测得到的最优参数。
- 本地模型推理前使用真实 tokenizer 硬校验；摘要预检查、Prompt 区段装箱和远程 API 预检查仍使用保守估算。

## Verification

- `python -m ruff check ...`：通过。
- 关联回归：`72 passed, 1 warning`。
- 全量 `python -m pytest -q`：`369 passed, 1 skipped, 3 warnings`，用时 `100.91s`。
- 警告来自 Starlette/httpx、LangGraph 和 jieba 依赖弃用提示；跳过项不属于本次功能失败。

## Next Steps

- 若继续模拟面试，从第 7 题动态摘要阈值的更新口径之后进入下一题。
- 未来可用长对话数据集校准 35% 与上下限，并另行设计 SQLite 原始消息保留/归档策略。

## Resume Prompt

读取 `AGENTS.md`、本文件和 `docs/interview/05_三大核心亮点模拟面试实录.md`；动态摘要水位已实现并通过全量测试，可继续模拟面试或按用户新任务推进。不要提交 `docs/learning/agent.json`、密钥与运行数据。
