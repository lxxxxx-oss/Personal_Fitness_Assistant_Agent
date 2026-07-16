# Codex Session State

> This file is the handoff anchor for this repository. It exists to prevent long Codex sessions from depending only on chat history or automatic context compaction.

## How To Use

At the start of a new Codex session, read this file before continuing work. If the file says there is an active task, recover from the checklist and referenced files instead of relying on compressed chat history.

During long or multi-step work, keep this file updated when any of the following happens:

- The task spans many files or more than one conversation turn.
- You are about to run tests, refactor shared logic, or edit interview-facing docs.
- The chat context is getting long enough that automatic compaction may trigger.
- You are about to pause, hand off, commit, or push.

Keep entries short, factual, and easy to resume. Do not paste long command output here.

## Current Task

Status: idle

Goal: 已按 P0→P1 完成现有代码收敛；未扩展业务功能。

Last updated: 2026-07-15

## Resume Checklist

- Read `AGENTS.md`.
- Read this file.
- Run `git status --short`.
- Inspect only the files listed under "Touched Files" and "Next Steps" before making edits.
- If previous work is marked active, continue from "Next Steps".

## Touched Files

- 本轮已修改：`app/main.py`、`app/api/schemas.py`、`app/config.py`、`app/llm/loader.py`、`app/graph/prompt_builder.py`、相关测试与文档
- `docs/README.md`、`项目总览.md`、`接口说明.md`、`运行与排错.md`、`项目证据.md`
- `docs/interview/` 当前学习资料
- `docs/miniprogram/` 当前状态与设计说明
- `docs/optimization/` 记忆/上下文设计与实施状态
- `docs/technical/` Router、Motion、ToolRegistry 专题和归档入口
- `.codex/SESSION_STATE.md`

## Important Decisions

- 当前事实优先级：代码/测试 → `项目总览`、`接口说明`、`运行与排错`、`项目证据` → interview → technical/optimization → archives。
- 所有能力统一区分“已实现、部分实现/当前边界、目标设计、历史归档”。
- Router 默认是规则、歧义处理和词面样例；embedding/Qwen 可选且默认关闭。
- 会话摘要保留最近 3 轮不压缩；Prompt 近期窗口默认最多 6 轮，两者不是同一参数。
- Memory Writer 当前只做显式写入；自动候选提取、语义冲突、pinned/token 分层预算、凭据拦截和 Milvus 删除同步均未冒充已实现。
- 小程序当前主协议为 WebSocket，HTTP 降级；未引用的 SSE parser 已删除。Motion 媒体链路已实现，正式样本、周期切分和专业规则仍是边界。

## Commands Run

- `python -m pytest -q` → `238 passed, 2 skipped, 1 warning`。
- `python -m ruff check app tests scripts`、`compileall`、Web UI JavaScript 语法检查均通过。
- Router eval → 常规 `66/66`、challenge 主/次/plan `36/36`、语义改写 `10/10`。
- `scripts/eval_memory_context.py --fail-on-fail` → `14/14`，其中摘要 `6/6`。
- 全部 39 个 Markdown：本地链接 0 断链、代码块 0 未闭合、编号 H2 0 重复、UTF-8 0 异常；`git diff --check` 无内容错误，仅有 Windows 行尾提示。

## Test / Verification State

- P0/P1 代码收敛与文档同步完成；没有执行用户侧浏览器或微信真机手工验收。
- 默认 pytest 会 mock 真实 LLM 和部分 embedding，不能替代回答质量与外部依赖验收。

## Next Steps

- 当前批次无必做项。建议下一步手工走一次 Web UI SSE 失败降级和小程序 WebSocket 冒烟测试，再决定是否提交。

## Resume Prompt

Read `AGENTS.md` and this file, then run `git status --short`. The P0/P1 code-convergence batch is complete; preserve the dirty worktree and continue only from the user's next request.
