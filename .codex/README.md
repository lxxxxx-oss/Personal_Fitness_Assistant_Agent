# Codex 项目配置

本目录由原 `.claude/` 配置迁移而来，用于保留原有协作逻辑，并让 Codex 能按项目约定工作。

## 迁移原则

- 原 Claude `auto-document` 技能迁移为 `.codex/skills/auto-document/SKILL.md`。
- 原 Claude `check-tool-spec` 技能迁移为 `.codex/skills/check-tool-spec/SKILL.md`。
- 原 Claude `settings.local.json` 中的命令白名单不再作为权限配置使用；Codex 权限由当前运行环境管理。常用命令沉淀在 `.codex/COMMANDS.md`。
- 项目级强约束写入根目录 `AGENTS.md`，Codex 后续修改代码时优先遵守。

## 使用方式

Codex 修改本项目时，应先读取根目录 `AGENTS.md`，再根据任务类型参考本目录下的技能说明。
