# 2026-06-25 Motion Step 2：姿态估计适配器

## 操作类型

功能新增 / 工具接口设计 / 文档维护。

## 背景

Motion Roadmap 的第二步是接入开源姿态估计能力，将后续图片/视频输入转换成统一 `PoseSequence`。本阶段先实现适配器边界，不开放图片/视频上传 API。

## 本次变更

新增代码：

- `app/tools/pose_estimator.py`
- `tests/test_pose_estimator.py`

更新代码：

- `app/tools/__init__.py`

更新文档：

- `docs/API.md`
- `docs/README.md`
- `docs/interview/motion/MOTION_MEDIA_PIPELINE_DESIGN.md`
- `docs/interview/motion/MOTION_OPTIMIZATION_ROADMAP.md`
- `docs/tests/2026-06-25-motion-pose-estimator-adapter.md`

## 实现内容

新增工具函数：

- `validate_image_array(image)`
- `estimate_pose_from_image(image, source_name=None, min_detection_confidence=0.5)`

设计取舍：

- 输入是 RGB `np.ndarray`，shape 为 `(H, W, 3)`。
- 工具只负责“图片数组 -> PoseSequence”，不负责 HTTP 上传、图片文件解码、动作评分或 LLM 解释。
- MediaPipe 使用懒加载；未安装 `mediapipe` 时返回 `CONFIG_MISSING`，不会影响现有功能。
- MediaPipe landmarks 转换为 `PoseSequence`：
  - `keypoints`: `x/y/z`
  - `confidence`: `visibility`
  - `source_type`: `image`
  - `pose_model`: `mediapipe_pose`
  - `joint_schema`: `mediapipe_33`

## 与预设路线的差异

预设路线是“第一版优先接入 MediaPipe Pose”。

实际实现先落地可选依赖适配器，没有把 MediaPipe 加成强依赖，也没有新增图片上传接口。这个差异是合理的：它能先稳定工具接口和错误处理，不破坏当前测试环境；真正的用户图片上传属于 Step 3。

## 工具接口规范检查

- 职责清晰：只做图片数组到 `PoseSequence` 的姿态估计适配。
- 输入清晰：RGB numpy array，shape `(H, W, 3)`；检测阈值为 `0.0~1.0`。
- 输出清晰：成功返回 `ToolResult.data = PoseSequence`；失败返回统一错误码。
- 权限清晰：不访问网络，不写文件；只在调用时懒加载本地 Python 依赖。
- 错误可处理：图片格式错误返回 `INVALID_PARAM`，依赖缺失返回 `CONFIG_MISSING`，未检测到人体返回 `DATA_NOT_FOUND`。

## 测试结果

已执行局部测试：

```bash
pytest tests/test_pose_estimator.py tests/test_pose_sequence.py tests/test_motion_tool.py -q
```

结果：

```text
17 passed
```

全量回归：

```bash
pytest -q
```

结果：

```text
87 passed, 1 skipped, 1 warning
```

## Next Steps

1. 进入 Step 3：实现图片静态姿态分析入口。
2. 决定图片文件解码依赖和上传接口形式。
3. 将图片上传结果返回为关键点摘要、低置信度提醒和静态姿态分析说明。
