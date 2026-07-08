# API 输入边界加固

## 问题

- API 文档声明图片最大 10MB，但后端原实现一次性读取完整图片，只在小程序端做前置校验。
- HTTP/SSE 使用 `ChatRequest` 限制 `user_id` 和 `message`，WebSocket 只检查非空，三种协议契约不一致。

## 修复

- 新增受限分块读取 helper，图片超过 `MAX_IMAGE_BYTES` 时返回 HTTP 413，不继续缓存完整请求体。
- WebSocket 使用 `ChatRequest.model_validate()` 复用 HTTP/SSE 的 1-64 与 1-4096 字符限制。
- WebSocket 字段非法时返回稳定的 `INVALID_REQUEST` 错误码，不向客户端暴露 Pydantic 内部细节。

## Tool Spec 检查

- 职责清晰：helper 只负责受限读取，不负责解码或姿态估计。
- 输入清晰：`UploadFile`、正整数上限和媒体标签。
- 输出清晰：成功返回 bytes，超限统一抛出 HTTP 413。
- 权限清晰：只读取本次用户上传，不访问其他文件或外部资源。
- 错误可处理：大小问题与格式、模型缺失分别使用 413、422、503。

## 测试

- 图片后端大小上限测试使用缩小后的常量验证越界行为。
- WebSocket 覆盖空值、超长值和错误类型，并断言与 HTTP 输入边界一致。
- 定向 API 测试：`25 passed, 1 warning`。
- 全量回归：`145 passed, 2 skipped, 1 warning`。
