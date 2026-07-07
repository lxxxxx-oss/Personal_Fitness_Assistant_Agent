# 小程序 Motion 图片上传专项验证

## 验证范围

- `/motion/analyze-image` 成功响应与 `mediapipe_image` 执行标签。
- 非图片输入拒绝行为。
- 小程序图片选择、大小检查、上传封装和结果展示代码语法。

## 自动化命令

```powershell
python -m pytest tests/test_api.py::TestMotionAnalyzeImageEndpoint -q -p no:cacheprovider
node --check miniprogram/pages/chat/chat.js
node --check miniprogram/utils/api.js
node --check miniprogram/utils/constants.js
node --check miniprogram/components/message-bubble/message-bubble.js
```

## 当前结果

- 图片接口定向测试：`2 passed, 1 warning`。
- 全量自动化回归：`129 passed, 2 skipped, 1 warning`。
- Python 编译与 JavaScript 语法检查通过。
- warning 为既有 Starlette TestClient/httpx 兼容层弃用提示。

## 待手工验收

- 开发者工具中的相册选择、相机拍摄、取消选择和超大图片提示。
- 真实 MediaPipe 模型下的清晰人体、多人/遮挡、无人图片结果。
- 真机 HTTPS、`uploadFile` 合法域名、隐私授权和弱网上传。
