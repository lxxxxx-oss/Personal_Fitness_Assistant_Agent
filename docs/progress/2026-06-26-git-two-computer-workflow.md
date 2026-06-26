# 2026-06-26 两台电脑 Git 协作流程记录

## 背景

项目目前需要在两台电脑之间切换开发和测试。此前一台电脑使用 `main`，另一台电脑保留过 `master`，并且出现过 unrelated histories、未跟踪文件阻止切换分支等问题。

## 本次维护内容

- 在 `docs/README.md` 的运维和开发命令中补充两台电脑协作流程。
- 在 `.codex/COMMANDS.md` 中补充每次工作前和工作后的 Git 命令，方便后续复制执行。
- 明确两台电脑统一使用 `main` 分支。

## 固定流程

每次开始工作前：

```bash
git checkout main
git status
git pull origin main
```

每次阶段性工作结束后：

```bash
git status
git add .
git commit -m "描述本次修改"
git push origin main
```

另一台电脑测试前：

```bash
git checkout main
git pull origin main
```

## 注意事项

- 如果 `git status` 显示有本地修改，先确认修改来源，再决定提交或暂存。
- 后续不要再在 `master` 分支继续开发，避免两台电脑分支状态再次分叉。
- 文档和代码变更都应通过 `main` 分支提交和推送。
