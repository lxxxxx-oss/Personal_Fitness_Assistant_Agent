# Motion 指标语义与坐标空间加固

## 问题

- 旧 `shape_difference` 将每帧姿态压缩为一个整体范数再比较，两个关节结构明显不同的姿态可能拥有相似范数。
- MediaPipe PoseSequence 可能使用 `world` 或 `normalized_image` 坐标，原兼容检查只比较 pose model 和 joint schema。

## 修复

- 复用 FastDTW 返回的时间对齐路径，对每对对应帧计算逐关节欧氏距离，再取全局均值作为 `shape_difference`。
- 在指标 metadata 公开 `shape_difference_definition=dtw_aligned_mean_joint_distance`。
- 图片和视频 PoseSequence 写入 `coordinate_space`；用户与参考均声明且不一致时拒绝比较。
- `/motion/references` 增加 `coordinate_space` 字段，便于查看标准样本来源。

## Tool Spec 检查

- 职责：只比较已结构化 PoseSequence，不承担动作诊断。
- 输入：要求 model/schema 一致，并拒绝已知坐标空间冲突。
- 输出：保留既有三项指标，metadata 明确形状差异定义。
- 权限：纯内存数值计算，不读写额外资源。
- 错误：兼容性问题返回 `INVALID_PARAM`，API 映射为 422。

## 边界

新指标仍是全局平均值，不能定位具体关节错误；`0.2` 等标签阈值仍需正式标准样本和教练标注校准。缺少 `coordinate_space` 的旧 `.npz` 为兼容保留，但其空间一致性不能得到同等保证。
