# 小程序 Motion 视频上传专项验证

## 验证范围

- `/motion/analyze-video` 成功响应与 `mediapipe_video` 执行标签。
- 不支持后缀的拒绝行为。
- 小程序视频选择、30MB 校验、上传进度、播放器和结果格式化代码语法。

## 自动化命令

```powershell
python -m pytest tests/test_api.py::TestMotionAnalyzeVideoEndpoint -q -p no:cacheprovider
node --check miniprogram/pages/chat/chat.js
node --check miniprogram/utils/api.js
node --check miniprogram/utils/constants.js
node --check miniprogram/components/message-bubble/message-bubble.js
```

## 当前结果

- 视频接口定向测试：`2 passed, 1 warning`。
- 全量自动化回归：`129 passed, 2 skipped, 1 warning`。
- Python 编译与 JavaScript 语法检查通过。
- warning 为既有 Starlette TestClient/httpx 兼容层弃用提示。

## 待手工验收

- 开发者工具和真机的视频选择、拍摄、取消及 30MB 提示。
- MP4/MOV/AVI 在目标设备和后端 OpenCV 构建中的实际兼容性。
- 上传进度、处理等待态、本地播放器和长结果滚动。
- 真实 MediaPipe 模型下有效帧比例和低质量视频 warning。
