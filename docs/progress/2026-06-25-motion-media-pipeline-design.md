# 2026-06-25 Motion 媒体输入技术路线文档化

## 操作类型

文档维护 / 需求分析 / 面试材料整理。

## 背景

Motion 子图当前支持 `.npz` 姿态序列上传分析，但普通用户更自然的输入是图片或视频。用户明确要求先把这一部分的技术路线和需求分析清楚，并作为面试亮点重点记录，同时遵守项目“面试导向”和文档维护规则。

## 本次变更

新增：

- `docs/interview/motion/MOTION_MEDIA_PIPELINE_DESIGN.md`

同步更新：

- `docs/interview/PROJECT_INTERVIEW_GUIDE.md`
- `docs/interview/SUBGRAPH_OPTIMIZATION_GUIDE.md`
- `docs/README.md`

后续补充：

- 将“用户上传图片/视频 -> 姿态估计模型 -> PoseSequence -> 必要时保存 `.npz` -> Motion 分析 -> LLM 解释”的完整流程写入面试文档。
- 明确 `.npz` 是内部持久化、调试、评测和标准动作库格式，不是普通用户必须直接接触的输入。
- 明确动作是否标准不是直接硬比关键点坐标，而是经过归一化、关节角度、轨迹、节奏和标准动作库相似度计算后再解释。
- 新增 `docs/interview/motion/MOTION_OPTIMIZATION_ROADMAP.md`，把 Motion 后续优化拆成 8 个步骤，并为每一步预留“当前状态、实际做法记录、偏差说明”，后续每推进一步都在该文档持续维护。

## 记录内容

本次文档明确区分了三类状态：

1. 当前已实现：
   - Motion 子图 `think -> parse -> tool -> check`。
   - `/motion/analyze` 的 `.npz` 上传分析。
   - 姿态归一化、FastDTW、余弦相似度、形状差异和结果解释。

2. 当前边界：
   - 没有标准动作库数据。
   - 没有图片/视频上传后的姿态估计适配层。
   - 没有自训练人体姿态估计模型。

3. 后续路线：
   - 定义 `PoseSequence` 中间格式。
   - 接入 MediaPipe Pose 作为第一阶段姿态估计模型。
   - 先支持图片静态姿态分析，再支持视频时序动作分析。
   - 用标准动作视频离线生成 `.npz` 标准动作库。
   - 建立姿态估计成功率、关键点连续性、标准动作对比稳定性和低质量媒体降级评测。

## 面试表达重点

推荐表述：

> 当前 Motion 已经完成“姿态序列进入系统之后怎么分析”的后半段能力；普通用户上传图片或视频时，需要先通过 MediaPipe Pose、MoveNet、RTMPose 或 OpenPose 这类成熟姿态估计模型转成统一 PoseSequence，再复用已有 Motion 分析工具。

不推荐表述：

> 系统已经支持用户上传视频自动分析深蹲。

原因：当前代码还没有实现图片/视频媒体接口，也没有接入姿态估计模型。文档必须避免把规划项说成已落地能力。

## 影响范围

- 仅更新文档。
- 未修改后端代码。
- 未新增或修改 API。
- 未新增测试。

## 验证

本次是文档变更，未运行自动化测试。

已通过文档一致性检查确认：

- README 中 Motion 状态已说明 `.npz` 分析已落地，媒体适配仍待补。
- 面试指南中 Motion 亮点已补充图片/视频路线，但没有夸大为已实现能力。
- 子图优化指南已把 Motion 优化顺序整理为可执行路线。

## Next Steps

1. 定义 `PoseSequence` 和 `.npz` metadata schema。
2. 设计 `app/tools/pose_estimator.py` 的职责、输入、输出和错误处理。
3. 评估是否先实现图片上传版 `/motion/analyze-media`。
4. 准备少量标准动作视频，用同一姿态估计模型离线生成标准 `.npz`。
