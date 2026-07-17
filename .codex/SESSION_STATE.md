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

Goal: 已完成文档一致性审计、自动化验证、服务级 E2E、5 分钟面试演示脚本和证据强弱防守清单。

Last updated: 2026-07-17

## Resume Checklist

- Read `AGENTS.md`.
- Read this file.
- Run `git status --short`.
- Inspect only the files listed under "Touched Files" and "Next Steps" before making edits.
- If previous work is marked active, continue from "Next Steps".

## Touched Files

- `README.md`
- `docs/项目总览.md`
- `docs/运行与排错.md`
- `docs/项目证据.md`
- `docs/interview/02_项目讲解与面试话术.md`
- `docs/interview/07_面试前速记.md`
- `docs/interview/09_简历项目描述优化记录.md`
- `.codex/COMMANDS.md`
- `.codex/SESSION_STATE.md`

## Important Decisions

- 当前事实优先级：代码/测试 → `项目总览`、`接口说明`、`运行与排错`、`项目证据` → interview → technical/optimization → archives。
- 所有能力统一区分“已实现、部分实现/当前边界、目标设计、历史归档”。
- Router 默认是规则、歧义处理和词面样例；embedding/Qwen 可选且默认关闭。
- 会话摘要保留最近 3 轮不压缩；Prompt 近期窗口默认最多 6 轮，两者不是同一参数。
- Memory Writer 当前只做显式写入；自动候选提取、语义冲突、pinned/token 分层预算、凭据拦截和 Milvus 删除同步均未冒充已实现。
- 小程序当前主协议为 WebSocket，HTTP 降级；未引用的 SSE parser 已删除。Motion 媒体链路已实现，正式样本、周期切分和专业规则仍是边界。

## Commands Run

- 文档一致性关键词扫描：旧机器绝对路径、旧测试数字、`TAVILY_API_KEY=mock`、Motion/RAG 过度表述未再命中现行文档。
- `python -m ruff check app tests scripts` → pass。
- `python -m compileall -q app tests scripts` → pass。
- Web UI JavaScript `node --check` → pass。
- Markdown 基础检查 → 48 files passed。
- Router eval → 常规 `66/66`、challenge 主/次/plan `36/36`、语义改写 `10/10`。
- `python scripts/eval_memory_context.py --fail-on-fail` → `14/14`，其中摘要 `6/6`。
- `python -m pytest -q` → `238 passed, 2 skipped, 1 warning`。
- `git diff --check` 无内容错误，仅有 Windows 行尾提示。
- 服务级 E2E（稳定 mock 环境）→ `/health` ok，`/ui/` 200；`/chat` 普通问答、Search mock、多意图 Search、MCP mock 通过；`/memory` 合法显式写入与搜索通过；`/motion/analyze` 3 帧/17 关节 `.npz` 通过；`/motion/references` 通过；`/chat/stream` 返回 SSE `meta/token/done`。
- 面试脚本文档 → 已补 5 分钟演示顺序、稳定启动配置、接口样例和边界收束；速记测试数字更新为 `238 / 2 / 1`。
- 证据强弱清单 → 已补后端 API、Router、RAG、Web UI、小程序、Motion、真实外部依赖的证据强度和防守口径；全仓严格 Markdown hygiene 命中旧归档/小程序文档既有尾随空格，`git diff --check` 对本轮改动通过。

## Test / Verification State

- 本轮批次已完成；尚未执行浏览器或微信真机手工验收。
- 默认 pytest 会 mock 真实 LLM 和部分 embedding，不能替代回答质量与外部依赖验收。

## Next Steps

- 当前批次无必做项。建议下一步做 Web UI 浏览器交互冒烟，或小程序真机/弱网验收。

## Resume Prompt

Read `AGENTS.md` and this file, then run `git status --short`. Current batch is complete; preserve existing README/docs/interview changes. If continuing, start from Web UI browser smoke testing or mini-program real-device/weak-network verification.
