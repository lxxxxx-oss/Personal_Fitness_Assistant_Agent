# Codex Session State

## Current Task

- Status: idle
- Goal: `docs/learning/` 技术事实审计与递进式学习口径修订已完成。
- Updated: 2026-07-27

## Completed

- 审计 `docs/learning/` 的入口与 11 篇学习资料，并以代码、配置和测试建立事实基线。
- 路由口径统一为代码中的五类分支：Chat、Diet、Search、Motion、MCP；RAG 是 Chat/Diet 共用的内部能力，不是第六类路由。
- RAG 口径统一为 SQLite + FAISS `IndexFlatIP` + BM25 + RRF；Hybrid 默认不做硬相似度阈值过滤，并区分当前评测入口、已完成烟测和待完成完整 RAGAS 基线。
- 记忆口径明确最近 6 轮、增量摘要、长期记忆候选确认、默认 FTS/LIKE 召回，以及可选且默认关闭的语义召回。
- 工具系统明确当前只有粗粒度权限标签、进程内审计、条件重试和可配置降级；硬超时、持久审计、租户鉴权属于生产化方向。
- 动作分析明确为 MediaPipe 单目姿态序列 + FastDTW 原型，不包装成多摄像头 3D 或专业教练评分系统。
- 学习路径统一为“零基础地图 → 技术总表 → 专题深挖 → 高频问答 → 模拟面试”，并补充四种能力状态标签。
- 未触碰被忽略的私人简历源文件 `docs/learning/agent.json`。

## Verification

- 全量：`286 passed, 1 skipped, 3 warnings`。
- `docs/learning/` 本地链接 45 个，缺失 0 个；旧目录路径残留 0 个。
- 关键默认值已与配置、路由、检索器、PromptBuilder、ToolRegistry 和评测脚本交叉核对。
- `git diff --check` 无空白错误，仅有 Windows 换行提示。

## Next Steps

1. 当前任务无待办；后续技术实现或简历口径变化时，同步维护 `docs/project/` 与 `docs/learning/`。
2. 完整 19 条真实生成与 RAGAS 三指标评测、Dense/Hybrid 对比仍是后续验证项，不应表述为已经完成。

## Resume Prompt

`docs/learning/` 技术事实审计已完成。先读 `AGENTS.md`、本文件和 `git status --short`；从 `docs/project/README.md` 查代码事实，从 `docs/learning/README.md` 进入学习资料。保留当前未提交变更，不要把待完成的完整 RAGAS 基线描述成已落地结果。
