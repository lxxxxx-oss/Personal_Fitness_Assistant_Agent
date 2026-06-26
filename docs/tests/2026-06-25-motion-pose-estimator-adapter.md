# 2026-06-25 Motion 姿态估计适配器测试记录

## 测试对象

Motion Step 2：`app/tools/pose_estimator.py`。

## 测试命令

```bash
pytest tests/test_pose_estimator.py tests/test_pose_sequence.py tests/test_motion_tool.py -q
```

## 测试内容

- RGB 图像数组 `(H, W, 3)` 可以通过输入校验。
- 灰度图等不符合 shape 的输入会被拒绝。
- 未安装 MediaPipe 时，`estimate_pose_from_image()` 返回 `CONFIG_MISSING`，不抛异常。
- 伪造 MediaPipe landmarks 可以转换为 `PoseSequence`。
- 生成的 `PoseSequence` 使用：
  - `source_type=image`
  - `pose_model=mediapipe_pose`
  - `joint_schema=mediapipe_33`
  - `confidence=visibility`

## 测试结果

局部测试：

```text
17 passed
```

全量回归：

```bash
pytest -q
```

```text
87 passed, 1 skipped, 1 warning
```

## 结论

通过。姿态估计适配器的接口边界、缺依赖降级和 landmark 到 `PoseSequence` 的转换逻辑已验证。当前尚未开放图片/视频上传 API。
