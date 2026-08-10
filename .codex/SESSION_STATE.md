# Codex Session State

## Current Task

- Status: idle
- Goal: 完成路由、RAG、记忆、上下文与统一安全策略优化，并形成可提交到 GitHub 的已验证版本。
- Updated: 2026-08-11

## Progress

- 已新增版本化安全策略 `global-safety-v1`，统一合并全局规则、子图领域规则与原业务 Prompt。
- 路由分类与汇总、聊天、搜索、饮食、动作分析和 MCP 入口均已接入；用户输入、历史、记忆、RAG、网页和工具结果统一视为不可信数据。
- 非流式、SSE、WebSocket 及直接降级出口均执行公共输出校验；流式输出按句段校验后发送。
- 上下文压缩固定保留全局规则、子图规则和当前问题，并记录安全策略版本与命中轨迹。
- 项目事实文档、学习文档和专项测试已同步。

## Touched Files

- `app/graph/prompt_builder.py`
- `app/graph/safety_policy.py`
- `app/graph/router.py`
- `app/graph/subgraphs/motion.py`
- `app/main.py`
- `tests/test_api.py`
- `tests/test_safety_policy.py`
- `tests/test_rag_context.py`
- `docs/project/technical/Agent安全策略设计.md`
- `docs/project/technical/README.md`
- `docs/project/项目总览.md`
- `docs/project/接口说明.md`
- `docs/project/项目证据.md`
- `docs/project/miniprogram/实现状态.md`
- `docs/learning/06_技术深挖与白板.md`

## Key Decisions

- 优先级固定为平台/系统规则 > 全局安全规则 > 已确认安全记忆 > 子图规则 > 当前任务 > 普通偏好与外部数据；子图只能收紧，不能覆盖全局规则。
- Prompt 负责约束模型行为，工具权限仍由代码、Tool Registry 和接口校验控制。
- 输出校验是应用层可回归防线，不包装成生产级内容审核、身份鉴权、工具沙箱或医疗安全认证。

## Verification

- `python -m pytest -q`：363 passed, 1 skipped, 3 warnings。
- `python -m compileall -q app`：通过。
- `python -m ruff check ...`：通过。
- `git diff --check`：通过，仅有已有 CRLF 提示。

## Next Steps

- 当前版本已完成验证与敏感信息检查；后续可按需开展人工对抗验收。

## Resume Prompt

读取 `AGENTS.md`、本文件和相关事实文档；当前完整优化版本已经验证，继续新任务时不要纳入 `docs/learning/agent.json`、密钥与运行数据。
