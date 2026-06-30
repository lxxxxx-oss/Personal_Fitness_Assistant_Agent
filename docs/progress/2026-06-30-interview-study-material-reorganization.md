# 2026-06-30 Interview 目录学习化整理

## 背景

`docs/interview/` 之前同时放了面试主讲稿、优化计划、技术设计、专题路线和状态台账。内容虽然完整，但学习时容易在“要背的内容”和“过程证据/设计原稿”之间来回跳转，不利于面试前复习。

本次整理的目标是：`docs/interview/` 只保留可以直接学习、背诵和应对面试的材料，并按重要级分类。

## 本次调整

### 保留在 `docs/interview/`

- `README.md`：面试背诵资料导航。
- `01_MUST_MASTER_PROJECT_STORY.md`：P0 必须掌握，项目主线和高频防守问题。
- `02_SHOULD_MASTER_TECH_QA.md`：P1 最好掌握，技术追问和基础知识。
- `03_GOOD_TO_KNOW_DEEP_DIVE.md`：P2 了解即可，深挖兜底、白板和反问。

### 移出 `docs/interview/`

- `PROJECT_INTERVIEW_GUIDE.md` -> `docs/technical/interview-archive/PROJECT_INTERVIEW_GUIDE_FULL.md`
- `SUBGRAPH_OPTIMIZATION_GUIDE.md` -> `docs/technical/interview-archive/SUBGRAPH_OPTIMIZATION_GUIDE.md`
- 当时将 `INTERVIEW_PREPARATION_OPTIMIZATION_PLAN.md` 移到 `docs/progress/`；当前进一步归档到 `docs/technical/interview-archive/INTERVIEW_PREPARATION_OPTIMIZATION_PLAN.md`。
- `router/*` -> `docs/technical/router/`
- `motion/*` -> `docs/technical/motion/`

## 整理原则

1. `interview/` 只放可直接背诵和复习的内容。
2. `technical/` 保留技术设计、路线图、历史长文档和专题状态。
3. `progress/` 保留计划、台账和阶段性记录。
4. 面试复习时优先按 P0 -> P1 -> P2 阅读，不再直接翻长文档。

## 测试说明

本次仅调整文档结构和学习资料，没有修改运行时代码，因此未执行自动化测试。
