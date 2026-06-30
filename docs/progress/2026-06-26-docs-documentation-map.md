# 2026-06-26 docs 文档脉络整理

## 操作类型

文档结构梳理。

## 背景

`docs/` 目录已经包含项目总览、API、面试讲解、专题路线、开发进度、测试记录、小程序文档和早期方案。文档数量增加后，需要一份更清晰的阅读地图，帮助快速判断：

- 面试复习应该先看哪些文档。
- 当前真实状态应以哪些文档为准。
- 历史记录、测试记录和专题路线分别承担什么职责。
- 后续修改代码时应该同步维护哪些文档。

## 本次变更

新增：

- `docs/DOCUMENTATION_MAP.md`

同步更新：

- `docs/README.md`
- `docs/API.md`

## 整理内容

`DOCUMENTATION_MAP.md` 按五层结构梳理了全部 docs：

- 顶层说明层：`README.md`、`API.md`
- 面试叙事层：`interview/`
- 专题路线层：`interview/motion/`、`interview/router/`、`miniprogram/`
- 演进证据层：`progress/`
- 验收证据层：`tests/`
- 历史方案层：`superpowers/`

同时补充了推荐阅读顺序、目录职责、两条主线和维护规则。

## 额外修正

- 在 `docs/README.md` 的保留文档说明中加入 `DOCUMENTATION_MAP.md`。
- 修正 `docs/API.md` 中后半段标题编号重复的问题。

## 验证

本次为纯文档整理，未运行自动化测试。

已通过命令检查新增文档入口和相关标题。
