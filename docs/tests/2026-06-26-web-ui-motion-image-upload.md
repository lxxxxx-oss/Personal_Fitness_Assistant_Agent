# 2026-06-26 Web UI Motion 图片上传测试记录

## 测试对象

Web UI 的 Motion 图片上传入口：

- `app/static/index.html`
- `/motion/analyze-image`

## 测试命令

JS 语法检查：

```bash
node -e "<extract script from app/static/index.html and compile with new Function>"
```

局部后端测试：

```bash
pytest tests/test_api.py::TestMotionAnalyzeImageEndpoint tests/test_pose_estimator.py -q
```

## 测试内容

- HTML 中的脚本可以被 JavaScript 引擎解析。
- UI 新增图片上传按钮和 file input。
- 图片上传函数会调用 `/motion/analyze-image`。
- 后端图片上传接口测试仍通过。
- MediaPipe 缺失时，前端会展示安装提示，不让用户只看到空白失败。

## 测试结果

```text
JS syntax OK
OK motion-image-btn
OK uploadMotionImage
OK /motion/analyze-image
OK image-input
8 passed, 1 warning
```

MediaPipe Tasks 兼容修复后复测：

```text
10 passed, 1 warning
```

二次兼容修复后复测：

```text
11 passed, 1 warning
```

全量回归：

```bash
pytest -q
```

```text
94 passed, 1 skipped, 1 warning
```

## 遗留风险

- 当前未执行真实浏览器截图验收。
- 当前本机 `mediapipe==0.10.35` 不暴露旧版 `mp.solutions`，需要使用 MediaPipe Tasks API。
- 若要验证完整姿态提取，需要准备 `pose_landmarker.task` 模型文件，并通过 `MEDIAPIPE_POSE_MODEL_PATH` 指向它，或放到 `data/models/pose_landmarker.task`。
- 当前 Codex 环境中后台启动 8001 服务未能稳定保持，建议手工测试时在终端前台运行 `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`。

## 2026-06-26 手工上传复测

用户在 Web UI 中上传图片后返回：

```text
Image analysis failed: MediaPipe Pose Landmarker model file is missing.
Download 'pose_landmarker.task' and set MEDIAPIPE_POSE_MODEL_PATH to its absolute path,
or place it at data\models\pose_landmarker.task.
```

结论：

- Web UI 图片上传入口已触发 `/motion/analyze-image`。
- 后端已进入 MediaPipe Tasks 路径，不再出现 `mp.solutions` 兼容性错误。
- 当前阻塞点是缺少 `pose_landmarker.task` 模型文件。
- 本次不修改代码，仅记录手工测试状态；下一步需要准备模型文件后再复测完整关键点提取。
