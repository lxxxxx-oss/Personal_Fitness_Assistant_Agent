# Motion 指标语义验收

## 覆盖

- 相同序列的 DTW、余弦和形状差异保持优秀。
- 整体范数相近但关节方向不同的姿态，新的形状差异能够识别偏差。
- model/schema 相同但 `coordinate_space` 不同的 PoseSequence 被拒绝。
- 图片适配器明确写入 `normalized_image` 坐标空间。

## 定向结果

```powershell
python -m pytest tests/test_motion_tool.py tests/test_pose_estimator.py tests/test_api.py::TestMotionAnalyzeVideoEndpoint -q -p no:cacheprovider
```

结果：`29 passed, 1 warning`。

全量回归：`147 passed, 2 skipped, 1 warning`。
