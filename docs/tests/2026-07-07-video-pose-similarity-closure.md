# Motion 视频 PoseSequence 相似度闭环验收

## 自动化范围

- 髋中心归一化的平移不变性。
- 不同关节数、不同 pose model、不同 joint schema 的拒绝行为。
- 相同 MediaPipe PoseSequence 的三项优秀指标。
- 标准视频构建器的 metadata、名称校验和防覆盖。
- `/motion/references` 兼容状态。
- `/motion/analyze-video` 的无参考、兼容参考和不兼容参考路径。

```powershell
python -m pytest tests/test_motion_tool.py `
  tests/test_motion_reference_builder.py `
  tests/test_api.py::TestMotionAnalyzeVideoEndpoint `
  -q -p no:cacheprovider
```

结果：`20 passed, 1 warning`。

全量自动化回归：`139 passed, 2 skipped, 1 warning`。

## 真实链路

```powershell
python scripts/build_motion_reference.py tmp/mediapipe_pose_sample.mp4 `
  --name warrior_pose_static `
  --library-dir tmp/motion_refs `
  --overwrite
```

随后调用 `/motion/references` 和带 `reference_name=warrior_pose_static` 的 `/motion/analyze-video`：

```text
reference: 15 frames / 33 joints / mediapipe_pose / mediapipe_33
comparison: HTTP 200
DTW: 0.0
cosine: 1.0
shape: 0.0
execution: mediapipe_video_similarity
```

## 遗留风险

- 同源满分只验证接线，不验证跨用户、跨视角和不同节奏下的阈值质量。
- 正式标准动作样本集尚未提交。
- 周期切分、关键点平滑和动作专项规则尚未实现。
- 小程序标准动作选择仍待开发者工具和真机验收。
