# 2026-06-26 Web UI 增加 Motion 图片上传入口

## 操作类型

前端功能新增 / 文档维护 / 测试执行。

## 背景

`/motion/analyze-image` 后端接口已经完成，但用户指出后续功能也需要同步到 UI 界面。为了让真实用户可以从 `/ui` 直接体验图片上传，本次在 Web UI 中新增 Motion 图片上传按钮。

## 本次变更

更新代码：

- `app/static/index.html`

更新文档：

- `docs/README.md`
- `docs/interview/motion/MOTION_OPTIMIZATION_ROADMAP.md`
- `docs/progress/2026-06-26-motion-image-static-analysis.md`
- `docs/tests/2026-06-26-web-ui-motion-image-upload.md`

## 实现内容

- 在输入栏新增隐藏 file input，支持 `image/png,image/jpeg`。
- 新增 `IMG` 上传按钮，用户选择图片后自动调用 `/motion/analyze-image`。
- 上传结果以 Motion 消息展示在聊天区。
- 展示内容包括：
  - 文件名
  - frames
  - joints
  - pose_model
  - joint_schema
  - confidence summary
  - warnings
  - message
- 如果 MediaPipe 未安装，会提示用户安装 `mediapipe` 并重启后端。

## 维护规则补充

后续新增后端用户可见能力时，需要同步检查 Web UI 是否要新增入口、状态展示或错误提示，不能只实现 API。

## 验证

已执行 JS 语法检查：

```bash
node -e "<extract script from app/static/index.html and compile with new Function>"
```

结果：

```text
JS syntax OK
```

已执行静态文件检查：

```text
OK motion-image-btn
OK uploadMotionImage
OK /motion/analyze-image
OK image-input
```

已执行图片接口相关自动化测试：

```bash
pytest tests/test_api.py::TestMotionAnalyzeImageEndpoint tests/test_pose_estimator.py -q
```

结果：

```text
8 passed, 1 warning
```

已执行全量回归：

```bash
pytest -q
```

结果：

```text
91 passed, 1 skipped, 1 warning
```

本次尝试在当前 Codex 环境中用后台方式启动 8001 服务，受本地 PowerShell 后台进程权限/环境限制影响，未能保持稳定后台运行。手工测试建议用户在终端前台执行启动命令。

## Next Steps

1. 启动后端后，通过 `http://127.0.0.1:8000/ui` 手工上传图片验证真实交互。
2. 若需要完整关键点提取，需要安装 `mediapipe` 并重启后端。
3. 后续实现视频上传时，同步在 Web UI 增加视频入口或统一媒体上传控件。

## 2026-06-26 手工测试反馈修复

用户在 UI 上传图片后遇到：

```text
MediaPipe pose estimation failed: module 'mediapipe' has no attribute 'solutions'
```

根因：

- 当前本机 `mediapipe==0.10.35` 只暴露 Tasks API，不再暴露旧版 `mp.solutions.pose`。
- 原适配器只调用 `mp.solutions.pose.Pose`，因此把版本兼容问题包装成了 `INTERNAL_ERROR`。

修复：

- `estimate_pose_from_image()` 先检测是否存在 `mp.solutions`。
- 如果存在，继续走旧版 Solutions API。
- 如果不存在，走 MediaPipe Tasks `PoseLandmarker` API。
- Tasks API 需要本地 `pose_landmarker.task` 模型文件；缺失时返回 `CONFIG_MISSING`，提示配置 `MEDIAPIPE_POSE_MODEL_PATH` 或放到 `data/models/pose_landmarker.task`。
- Web UI 错误提示已同步更新，不再只提示 `pip install mediapipe`。

二次修复：

- 用户重启后仍遇到 `mp.solutions` 报错，说明 `hasattr(mp, "solutions")` 在部分安装环境中仍不够稳。
- 已改为显式 import `mediapipe.solutions.pose` / `mediapipe.python.solutions.pose`。
- 只有旧版 pose 模块真实可导入时才走 legacy Solutions API，否则直接走 Tasks API。
- 本地复测 `estimate_pose_from_image()` 已返回 `CONFIG_MISSING: pose_landmarker.task missing`，不再出现 `mp.solutions` 异常。

验证：

```bash
pytest tests/test_pose_estimator.py tests/test_api.py::TestMotionAnalyzeImageEndpoint -q
```

```text
10 passed, 1 warning
```

```bash
pytest -q
```

```text
93 passed, 1 skipped, 1 warning
```

二次修复后复测：

```bash
pytest tests/test_pose_estimator.py tests/test_api.py::TestMotionAnalyzeImageEndpoint -q
pytest -q
```

```text
11 passed, 1 warning
94 passed, 1 skipped, 1 warning
```

## 2026-06-26 手工上传复测记录

用户再次通过 Web UI 上传图片后返回：

```text
Image analysis failed: MediaPipe Pose Landmarker model file is missing.
Download 'pose_landmarker.task' and set MEDIAPIPE_POSE_MODEL_PATH to its absolute path,
or place it at data\models\pose_landmarker.task.
```

状态判断：

- UI 上传按钮和 `/motion/analyze-image` 调用链路已走通。
- `mp.solutions` 兼容性问题已解决。
- 当前没有完成真实关键点提取，因为缺少 MediaPipe Tasks 所需的 `pose_landmarker.task` 模型文件。
- 本次按用户要求只记录，不进行代码修改。
