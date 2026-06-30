# 2026-06-26 docs 索引化减负整理

## 操作类型

文档结构优化。

## 背景

`docs/` 下的文档数量较多，但大部分内容都有价值，不能简单删除。当前主要问题是入口过多，导致阅读压力大；更合适的处理方式是减少日常入口，把日期记录和测试记录保留为二线证据。

## 本次变更

新增：

- `docs/progress/README.md`
- `docs/tests/README.md`

同步更新：

- `docs/DOCUMENTATION_MAP.md`
- `docs/README.md`

## 整理思路

采用“冷热分层”：

- 一线入口：`README.md`、`API.md`、`DOCUMENTATION_MAP.md`、`interview/PROJECT_INTERVIEW_GUIDE.md`
- 二线专题：`interview/`、`miniprogram/`
- 三线证据：`progress/`、`tests/`
- 历史方案：`superpowers/`

`progress/README.md` 按主题索引阶段记录，`tests/README.md` 按能力整理验收矩阵。单篇日期文档仍然保留，但日常不需要逐个打开。

## 影响范围

- 仅修改文档结构和阅读入口。
- 未修改代码。
- 未修改 API。
- 未修改测试。

## 验证

本次为纯文档整理，未运行自动化测试。

已检查新增索引文件、顶层 README 入口和文档地图引用。
