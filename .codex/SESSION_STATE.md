# Codex Session State

## Current Task

- Status: idle
- Goal: 核对当前阶段改动、运行提交前验证并推送到 GitHub。
- Updated: 2026-07-30

## Progress

- 已核对当前公开 API、Web UI 交互、模型目录、外部依赖和 Motion 素材边界。
- 已新增 `docs/project/手动验收测试清单.md`，覆盖真实 API、离线演示、网页交互、全部 Agent 能力、RAG、记忆、动作、HTTP/SSE/WebSocket、降级与小程序补充验收。
- 已同步 `docs/project/README.md` 和 `docs/project/运行与排错.md` 的入口。
- 当前阶段的 DeepSeek 模型切换、Web UI、Agent 执行轨迹、测试与文档已完成提交前核对，准备推送 GitHub。

## Key Decisions

- 真实 DeepSeek、Tavily、mock MCP 和本地 Qwen 分开验收，不能把降级结果记成真实外部调用成功。
- 当前 `data/motions/squat.npz` 与 MediaPipe 图片/视频 schema 不兼容；清单必须明确“姿态提取成功”不等于“标准动作相似度成功”。
- Web/FastAPI 作为本清单主线，小程序仅提供独立补充验收入口。

## Verification

- 全部 Markdown 相对链接检查通过。
- 文档代码围栏成对，公开 API 路径已与 `app/main.py` 复核。
- `git diff --check` 通过，仅有仓库既有的 LF/CRLF 提示。
- 提交前全量回归：`301 passed, 1 skipped, 3 warnings`。
- `docs/learning/agent.json` 仍由 `.gitignore` 排除，未发现形似真实 API Key 的待提交内容。
- 本轮编写的是可执行测试方案，未把尚未实际执行的项目功能登记为通过证据。

## Next Steps

- 后续按手动验收清单补齐 Tavily、真实 MCP、本地 Qwen 与图片/视频动作素材的真实证据。

## Resume Prompt

先读 `AGENTS.md`、本文件和 `git status --short`。当前阶段已完成自动化回归与 GitHub 推送；下一步按手动验收清单补齐尚未验证的真实外部依赖和媒体链路。
