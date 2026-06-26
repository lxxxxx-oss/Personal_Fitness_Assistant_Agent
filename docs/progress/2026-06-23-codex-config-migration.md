# Codex 配置迁移记录

## 时间戳

2026-06-23

## 操作类型

配置变更 / 文档维护

## 背景

项目最初由 Claude 编写，根目录中存在 `.claude/` 配置：

- `.claude/settings.local.json`：Claude 本地命令权限白名单。
- `.claude/skills/auto-document/skill.md`：自动维护 docs 的技能。
- `.claude/skills/check-tool-spec/SKILL.md`：工具设计规范检查技能。

这些配置对 Claude 有效，但 Codex 不读取 Claude 的本地权限和技能目录。为了让后续 Codex 修改代码时能保留原有协作逻辑，需要迁移为 Codex 可用的项目配置。

## 变更概述

新增 Codex 配置目录：

```text
.codex/
├── README.md
├── COMMANDS.md
└── skills/
    ├── auto-document/
    │   └── SKILL.md
    └── check-tool-spec/
        └── SKILL.md
```

新增/更新项目协作入口：

- `AGENTS.md`：作为 Codex 的项目级协作规则入口。
- `docs/README.md`：补充 Codex 配置说明。

清理 Claude 配置：

- 删除 `.claude/settings.local.json`。
- 删除 `.claude/skills/auto-document/skill.md`。
- 删除 `.claude/skills/check-tool-spec/SKILL.md`。
- 删除空的 `.claude/` 目录。

## 迁移逻辑

| Claude 配置 | Codex 对应 |
|---|---|
| `.claude/skills/auto-document/skill.md` | `.codex/skills/auto-document/SKILL.md` |
| `.claude/skills/check-tool-spec/SKILL.md` | `.codex/skills/check-tool-spec/SKILL.md` |
| `.claude/settings.local.json` | `.codex/COMMANDS.md` 命令参考 |
| Claude 隐式项目规则 | `AGENTS.md` 显式项目规则 |

原配置的底层逻辑保持不变：

- 代码修改后同步维护 `docs/`。
- 接口变更同步 `docs/API.md`。
- 项目进度、运行方式、问题处理同步 `docs/README.md`。
- 小程序相关改动同步检查 `docs/miniprogram/`。
- 工具/函数设计按职责、输入、输出、权限、错误处理五项标准审查。

## 影响范围

影响配置和文档，不影响业务代码。

涉及文件：

- `AGENTS.md`
- `.codex/README.md`
- `.codex/COMMANDS.md`
- `.codex/skills/auto-document/SKILL.md`
- `.codex/skills/check-tool-spec/SKILL.md`
- `docs/README.md`
- `docs/progress/2026-06-23-codex-config-migration.md`

## 验证结果

- 已确认 `.codex/` 目录存在且包含迁移后的技能和命令参考。
- 已确认 `.claude/` 目录删除。
- 已确认 `AGENTS.md` 包含 Codex 项目协作规则。
- 已确认 `docs/README.md` 包含 Codex 配置说明和文档维护约定。

## Next Steps

后续 Codex 修改本项目时：

1. 优先读取 `AGENTS.md`。
2. 根据任务类型参考 `.codex/skills/`。
3. 如果代码修改影响项目说明、接口、运行方式、问题处理或测试状态，同步更新对应 docs 文档。
