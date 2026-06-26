# 2026-06-26 Motion 图片静态姿态分析测试记录

## 测试对象

Motion Step 3：`/motion/analyze-image` 图片静态姿态分析入口。

覆盖代码：

- `app/main.py`
- `app/tools/pose_estimator.py`
- `tests/test_api.py`
- `tests/test_pose_estimator.py`

## 测试命令

```bash
pytest tests/test_pose_estimator.py tests/test_pose_sequence.py tests/test_api.py::TestMotionAnalyzeImageEndpoint -q
```

## 测试内容

- PNG 图片字节可以通过 Pillow 解码为 RGB numpy array。
- 不支持的图片后缀会被拒绝。
- `/motion/analyze-image` 可以接收图片上传，并返回静态姿态摘要。
- API 成功路径通过 monkeypatch 模拟 MediaPipe 结果，避免测试依赖真实模型。
- 响应包含 frames、joints、pose_model、joint_schema、confidence_summary、warnings 和 message。
- 非图片后缀上传返回 422。

## 测试结果

局部测试：

```text
13 passed, 1 warning
```

全量回归：

```bash
pytest -q
```

```text
91 passed, 1 skipped, 1 warning
```

warning 来源：

```text
StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated
```

该 warning 来自测试依赖版本，不影响本次图片接口功能判断。

## 结论

通过。图片上传到 `PoseSequence(T=1)` 的静态姿态分析入口已验证。当前接口不做视频时序分析，也不做完整动作质量判断。
