# 2026-06-25 Motion Step 1：PoseSequence 中间格式

## 操作类型

功能新增 / 工具接口设计 / 文档维护。

## 背景

Motion Roadmap 的第一步是定义统一姿态数据格式 `PoseSequence`。这个格式用于承接后续图片/视频姿态估计输出，并向现有 Motion 分析算法提供稳定输入。

## 本次变更

新增代码：

- `app/tools/pose_sequence.py`
- `tests/test_pose_sequence.py`

更新代码：

- `app/tools/motion_tool.py`
- `app/tools/__init__.py`

更新文档：

- `docs/API.md`
- `docs/README.md`
- `docs/interview/motion/MOTION_MEDIA_PIPELINE_DESIGN.md`
- `docs/interview/motion/MOTION_OPTIMIZATION_ROADMAP.md`
- `docs/tests/2026-06-25-motion-pose-sequence-schema.md`

## 实现内容

新增 `PoseSequence` dataclass：

```text
keypoints: (T, J, C)
fps
source_type
pose_model
joint_schema
confidence
metadata
```

新增 helper：

- `validate_pose_sequence()`
- `pose_sequence_to_npz_payload()`
- `pose_sequence_from_npz()`

`load_npz_pose()` 现在会复用 `PoseSequence` schema：

- 支持推荐 key：`keypoints`。
- 兼容旧 key：`pose`、`positions`。
- 支持 metadata：`fps`、`source_type`、`pose_model`、`joint_schema`、`confidence`、`meta_*`。
- 保持原有返回行为：成功时仍返回 `(T, J, 3)` ndarray，避免破坏 `/motion/analyze` 和 Motion 子图。

## 与预设路线的差异

预设路线只要求定义 `PoseSequence` 和 `.npz` metadata schema。

实际实现额外把 schema 接入了现有 `load_npz_pose()`。这个差异是正向的，因为它让新格式不只是文档定义，而是已经进入当前 Motion 分析入口，同时保持旧接口兼容。

## 工具接口规范检查

- 职责清晰：`PoseSequence` 只负责姿态序列数据契约，不做姿态估计、不做动作评分。
- 输入清晰：核心输入为 numpy array，shape 为 `(T, J, C)`，并校验数值类型、有限值、最小帧数、最小关键点数。
- 输出清晰：成功返回 `ToolResult.data = PoseSequence`，失败返回统一 `ErrorCode.INVALID_PARAM` 或 `DATA_NOT_FOUND`。
- 权限清晰：不访问网络，不调用外部模型，不做文件删除；`.npz` 读写 payload 由调用方决定。
- 错误可处理：shape、dtype、NaN/Inf、confidence 对齐错误均返回可解释错误。

## 测试结果

已执行：

```bash
pytest tests/test_pose_sequence.py tests/test_motion_tool.py tests/test_api.py::TestMotionAnalyzeEndpoint -q
```

结果：

```text
15 passed, 1 warning
```

全量回归：

```bash
pytest -q
```

结果：

```text
83 passed, 1 skipped, 1 warning
```

## Next Steps

1. 设计 `app/tools/pose_estimator.py`，准备接入 MediaPipe Pose。
2. 先实现图片静态姿态分析，验证 `image -> PoseSequence -> motion_tool` 链路。
3. 后续再扩展到视频抽帧和标准动作库生成。
