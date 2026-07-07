# WebSocket 真流式与黄金媒体链路验收

## 自动化验证

```powershell
python -m pytest tests/test_api.py::TestChatEndpoint -q -p no:cacheprovider
```

结果：`7 passed, 1 warning`。

全量自动化回归：`130 passed, 2 skipped, 1 warning`。

关键用例将生成器停在第二个 token 之前，并断言：

- 第一个 token 已进入 WebSocket `send_json`。
- 整体流式任务仍未完成。
- 释放生成器后，第二个 token 到达且最终回复拼接正确。

这个断言可以阻止代码退回 `list(generate_stream(...))` 的伪流式实现。

## 真实 MediaPipe 冒烟

使用本地 `data/models/pose_landmarker.task`、真实图片和真实短视频，通过 FastAPI TestClient 调用公开接口：

```text
image 200 1 33 motion·mediapipe_image
video 200 15 15 1.0 motion·mediapipe_video
```

结论：图片和视频均经过真实 MediaPipe 推理并返回公开响应，不是 mock estimator。

## 未覆盖

- 微信开发者工具与真机 WebSocket 首 token 体感。
- HTTPS、合法域名、隐私授权和弱网上传。
- 真实 Qwen 长回复的首 token/P95 定量基线。
