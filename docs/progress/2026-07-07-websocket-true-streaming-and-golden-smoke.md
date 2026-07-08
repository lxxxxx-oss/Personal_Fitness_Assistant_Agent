# 黄金演示闭环阶段 4：WebSocket 真流式与真实媒体冒烟

## 阶段目标

修复 WebSocket 表面逐 token、实际等待完整生成结束后才开始发送的问题，并用本机真实 MediaPipe 模型和真实图片/视频样本重新验证黄金媒体链路。

## 根因

旧实现把同步 `generate_stream()` 放到线程中后立刻调用 `list(...)`，虽然避免阻塞 asyncio 事件循环，但也把全部 token 缓存在内存中。客户端只能在模型完整生成后收到第一段内容，失去了流式输出降低首 token 等待的意义。

## 修复方案

- 同步生成器继续放在工作线程，避免模型推理阻塞事件循环。
- 工作线程每产生一个 token，立即投递到 asyncio queue。
- WebSocket 协程从 queue 消费并立刻发送 `token` 消息，同时累积最终回复用于记忆。
- 客户端断开或发送失败时设置停止标记并取消桥接任务，避免继续向失效连接发送。
- 生成器异常通过 queue 回传给现有 WebSocket error 协议处理。

## 接口设计检查

- 职责：桥接函数只负责同步 token 生成器到 WebSocket 的实时转发。
- 输入：已创建的 WebSocket、实现 `generate_stream()` 的 LLM 和最终 prompt。
- 输出：逐 token 协议保持不变，函数返回完整回复供记忆写入。
- 权限：不新增网络目标、文件或敏感信息访问。
- 错误处理：生成异常、断连和任务取消均有明确路径，不吞掉异常。

## 当前验证

- Chat/WebSocket 定向测试：`7 passed, 1 warning`。
- 全量自动化回归：`130 passed, 2 skipped, 1 warning`。
- 首 token 测试会阻塞第二个 token，确认第一个 token 已发送且生成任务尚未结束。
- 真实图片：HTTP 200，`1` 帧、`33` 关键点、`mediapipe_image`。
- 真实视频：HTTP 200，`15/15` 有效帧、有效帧比例 `1.0`、`mediapipe_video`。

## 当前边界

- 本次真实冒烟属于本机后端 API 级验证，不等于微信开发者工具或真机验收。
- SSE 仍直接迭代同步生成器；当前主小程序链路使用 WebSocket，后续若扩展高并发 SSE 需要采用同类异步桥接。
- 本地 Qwen 生成仍由共享模型锁串行化，多用户并发需要独立推理服务。

## 下一步

在微信开发者工具和真机配置 HTTPS、request/socket/uploadFile 合法域名及隐私声明，完成聊天、图片、视频、错误和弱网路径的最终验收。
