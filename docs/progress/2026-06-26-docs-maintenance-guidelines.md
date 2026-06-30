# 2026-06-26 文档维护准则收口

## 操作类型

文档规范整理。

## 背景

`docs/` 目录已经按一线入口、二线专题、三线证据进行索引化整理，但“什么时候维护什么类型的文档”的规则仍分散在 `README.md`、`DOCUMENTATION_MAP.md`、`progress/README.md` 和 `tests/README.md` 中。

需要把维护准则收口成一套可执行规则，避免后续修改代码或文档时不知道该同步哪些材料。

## 本次变更

更新：

- `docs/DOCUMENTATION_MAP.md`
- `docs/README.md`
- `docs/progress/README.md`
- `docs/tests/README.md`

新增：

- `docs/progress/2026-06-26-docs-maintenance-guidelines.md`

## 整理内容

在 `DOCUMENTATION_MAP.md` 中新增完整维护准则：

- 什么时候必须维护文档。
- 不同变更类型应该更新哪些文档。
- 一线事实源和二线证据的优先级。
- 新增 progress/tests 记录后的同步规则。
- 哪些边界不能写错。

`README.md` 保留简要维护规则，并链接到完整准则，避免顶层文档过长。

`progress/README.md` 和 `tests/README.md` 只保留目录内的补充维护规则，强调新增记录后要同步索引。

## 验证

本次为纯文档整理，未运行自动化测试。

已检查维护准则入口、README 链接和 progress/tests 索引说明。
