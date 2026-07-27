# Codex 项目配置

本目录由原 `.claude/` 配置迁移而来，用于保留原有协作逻辑，并让 Codex 能按项目约定工作。

## 迁移原则

- 原 Claude `auto-document` 技能迁移为 `.codex/skills/auto-document/SKILL.md`。
- 原 Claude `check-tool-spec` 技能迁移为 `.codex/skills/check-tool-spec/SKILL.md`。
- 原 Claude `settings.local.json` 中的命令白名单不再作为权限配置使用；Codex 权限由当前运行环境管理。常用命令沉淀在 `.codex/COMMANDS.md`。
- 项目级强约束写入根目录 `AGENTS.md`，Codex 后续修改代码时优先遵守。
- `.codex/config.toml` 设置项目级自动压缩阈值和工具输出上限，`.codex/compact_prompt.md` 约束压缩摘要内容。
- `.codex/SESSION_STATE.md` 保存短期任务检查点，用于当前任务续航、自动压缩失败或新任务续接。
- 项目文档采用双入口：`docs/project/README.md` 面向代码 Agent 和项目维护，`docs/learning/README.md` 面向用户学习与面试准备；两者的职责关系由 `docs/README.md` 说明。
- 用户说“提前帮我压缩上下文”时，Codex 会自动写检查点和短交接摘要；当前客户端内部压缩仍需用户随后输入 `/compact`。`/compact` 成功后默认继续当前任务，只有压缩失败、上下文仍高或后续工作范围明显扩大时才建议新建任务。

## 使用方式

Codex 修改本项目时，应先读取根目录 `AGENTS.md` 和 `.codex/SESSION_STATE.md`，运行 `git status --short`，再通过 `docs/project/README.md` 定位当前事实；只有学习、简历或面试任务才进入 `docs/learning/README.md`。之后按任务类型参考本目录下的技能说明。项目级配置仅在仓库被标记为 trusted 时加载，修改启动期配置后应新建任务验证。

如果调整文档目录或文件名，还必须联动检查 `AGENTS.md`、根 `README.md`、`.gitignore`、本目录的恢复规则和技能文件，并验证全仓库不存在旧路径引用。
