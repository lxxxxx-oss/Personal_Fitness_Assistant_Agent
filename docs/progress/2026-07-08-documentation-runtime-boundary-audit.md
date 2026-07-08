# 文档与运行时边界审计

## 目标

依据当前代码重新核对 Memory、Motion 媒体入口、关节角和 ReAct 表述，修复“结构存在”被写成“能力已贯通”的口径偏差。

## 代码事实

- `SlidingWindowMemory` 按 `user_id` 最多保存 6 轮，但只有 Chat 子图读取 `memory`，且只注入最后 6 条消息。
- 图片、视频和 `.npz` 上传由独立 FastAPI Motion 接口直接调用工具，不经过 `/chat` Router。
- `compute_joint_angles()` 是已实现的通用计算原语，尚未接入媒体响应和动作专项规则。
- Motion 子图按固定边执行一次 `think -> parse -> tool -> check`，没有 observation 后重新规划的多轮循环。

## 文档调整

- 修正项目 README 的 Memory 与 Motion 当前状态。
- 修正 interview 入口、技术索引、主线、问答和一页速记。
- 在 Motion 媒体设计中增加独立 API 与对话子图的架构边界。

## 影响

本次只调整文档，不改变接口和运行行为。修正后的面试口径能够明确区分：缓冲区与实际上下文消费、媒体工具链与 Agent 编排、算法原语与已接入指标、ReAct 思想与完整自主循环。
