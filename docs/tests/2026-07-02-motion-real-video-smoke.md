# 2026-07-02 Motion 真实视频最小链路验收

## 测试目标

验证以下真实链路：

```text
MP4 上传 -> OpenCV 抽帧 -> MediaPipe VIDEO 模式
-> PoseSequence(T=N) -> /motion/analyze-video
```

本轮只验证视频到多帧姿态序列，不验证动作周期、标准动作相似度或专项纠错。

## 安全与资源边界

- 支持 `.mp4`、`.mov`、`.avi`。
- 上传大小上限为 30 MB。
- 默认目标采样率约 10 FPS。
- 单次最多处理 300 个采样帧。
- 上传写入临时文件，请求结束后删除。
- 未检测到人体的帧跳过，并返回有效帧率。

## 自动化测试

```text
16 passed, 1 warning
```

覆盖视频接口成功响应和非法后缀拒绝，以及既有 PoseSequence 与图片姿态适配测试。

全量回归：

```text
122 passed, 2 skipped, 1 warning
```

## 真实模型验收

使用已完成真实图片验收的人体样例生成 30 帧、15 FPS 的短 MP4，再通过 HTTP 上传。该视频用于验证真实视频解码和多帧推理，不代表真实健身动作评测样本。

```text
POST /motion/analyze-video
HTTP 200

source_type=video
frames=15
joints=33
effective_fps=7.5
sampled_frames=15
valid_frame_ratio=1.0
confidence_mean=0.9926
```

## 结论

最小视频上传链路已真实打通。下一阶段仍需实现关键点平滑、缺失帧插值、动作周期切分、标准动作库和专项动作规则，当前接口不能表述为“已完成视频动作质量分析”。
