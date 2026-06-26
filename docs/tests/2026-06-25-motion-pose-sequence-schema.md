# 2026-06-25 Motion PoseSequence 测试记录

## 测试对象

Motion Step 1：`PoseSequence` 中间格式与 `.npz` 兼容加载。

覆盖代码：

- `app/tools/pose_sequence.py`
- `app/tools/motion_tool.py`
- `/motion/analyze` 的 `.npz` 上传兼容性

## 测试命令

```bash
pytest tests/test_pose_sequence.py tests/test_motion_tool.py tests/test_api.py::TestMotionAnalyzeEndpoint -q
```

## 测试内容

- `PoseSequence` 接收 `(T, J, C)` keypoints、fps、source_type、pose_model、joint_schema、confidence 和 metadata。
- 非数值 keypoints 会被拒绝。
- `PoseSequence -> .npz payload -> PoseSequence` 可以保留 metadata。
- 旧 `.npz` key `pose` 仍可被 `load_npz_pose()` 加载。
- 带 visibility/confidence 等额外坐标的 `(T, J, 4)` 数据进入当前分析层时会取前三维，保持 Motion 算法兼容。
- `/motion/analyze` 原有 `.npz` 上传行为未被破坏。

## 测试结果

局部测试：

```text
15 passed, 1 warning
```

全量回归：

```bash
pytest -q
```

```text
83 passed, 1 skipped, 1 warning
```

warning 来源：

```text
StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated
```

该 warning 来自测试依赖版本，不影响本次 Motion schema 功能判断。

## 结论

通过。`PoseSequence` schema 已可作为后续图片/视频姿态估计适配层的内部数据契约，同时保持现有 `.npz` 分析接口兼容。
