# Codex Session State

## Current Task

- Status: idle
- Goal: 动作媒体与 Router 串联已形成阶段检查点；前三步后端链路完成，第四步 Web UI 自动引用待续。
- Updated: 2026-08-24

## Progress

- 第一步已完成：新增公共 Motion 分析服务，图片/视频端点已复用。
- 原有 HTTP 请求、响应和状态码映射保持不变。
- 第二步已完成：新增只保存结构化分析结果的 SQLite 临时制品层，支持 TTL、用户/会话归属检查和软删除。
- 图片/视频接口只有显式传入 `user_id` 才创建制品；不传时保持原响应行为。
- 已提供受归属保护的 GET/DELETE 制品接口。
- 第三步已完成：HTTP、SSE、WebSocket 的 `ChatRequest` 可引用最多 3 个动作制品，统一校验后注入 RouterState，并确定性进入 motion 子图消费结构化摘要。
- 第四步已开始并完成前端现状检查：当前网页仍直接调用 `/motion/analyze-image` 或 `/motion/analyze-video` 并独立渲染分析卡片，尚未将 `artifact_id` 写入聊天请求。
- 第四步尚未产生业务代码或文档改动；本次已统一记录当前停点，后续从 Web UI 自动引用继续。

## Touched Files

- `.codex/SESSION_STATE.md`
- `app/main.py`
- `app/api/schemas.py`
- `app/graph/router.py`
- `app/graph/state.py`
- `app/graph/subgraphs/motion.py`
- `app/config.py`
- `app/memory/media_artifact_store.py`
- `app/services/__init__.py`
- `app/services/motion_analysis.py`
- `tests/test_config.py`
- `tests/test_media_artifact_store.py`
- `tests/test_motion_artifact_api.py`
- `tests/test_motion_analysis_service.py`
- `tests/test_motion_chat_artifact.py`
- `docs/project/接口说明.md`
- `docs/project/运行与排错.md`
- `docs/project/项目总览.md`
- `docs/project/technical/motion/动作媒体链路设计.md`
- `docs/project/technical/motion/动作分析优化路线.md`
- `docs/project/项目证据.md`

## Key Decisions

- 公共服务保持单一职责，使用结构化输入输出与可处理错误；API 层继续负责 HTTP 校验与响应映射。
- 第一阶段必须保持 `/motion/analyze-image`、`/motion/analyze-video`、`/motion/analyze` 的请求响应兼容。
- 服务层不负责上传限制、临时文件、鉴权、持久化或 LLM 解释；后续 Router 可直接复用服务而不反向调用 HTTP。
- 制品只保存分析摘要，不保存原图、视频或关键点；默认 TTL 60 分钟，可配置为 1–1440 分钟。
- 当前 `user_id` 是逻辑归属标识，不冒充账号认证；生产化需由可信登录态注入。
- 聊天请求只引用已有制品，统一准备阶段校验归属、会话绑定和有效期；失败统一表现为未找到，避免泄露其他用户制品是否存在。
- motion 子图只消费结构化分析摘要，不重读原始媒体、不重复运行 MediaPipe。

## Verification

- 第三步专项：54 passed；聊天接口联合回归：93 passed。
- 全量：389 passed, 1 skipped, 3 warnings。
- Ruff、compileall 和 `git diff --check` 通过（仅换行提示）。

## Next Steps

- 恢复动作媒体串联任务时继续第四步：Web UI 上传图片/视频时携带逻辑用户/会话信息，读取返回的 `artifact_id`，再通过同一次聊天请求的 `motion_artifact_ids` 交给 Router；上传失败保留附件供重试。
- 第四步实现后补充 Web UI 静态契约测试、后端联合回归和动作媒体链路事实文档，并按约定停止等待确认。

## Resume Prompt

读取 `AGENTS.md` 与本文件；若恢复动作媒体串联任务，从第四步继续：前端上传获得 `artifact_id` 后随聊天请求发送 `motion_artifact_ids`，不再把独立分析卡作为最终回答；完成后更新测试、文档并停下等待确认。
