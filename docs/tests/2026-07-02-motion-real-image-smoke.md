# 2026-07-02 Motion 真实图片最小链路验收

## 测试目标

验证 Motion 图片能力不再只停留在 Mock 测试，打通以下真实链路：

```text
官方人体样例图
  -> Pillow RGB 解码
  -> MediaPipe Pose Landmarker
  -> PoseSequence
  -> POST /motion/analyze-image
  -> 静态姿态摘要
```

## 环境与模型

- Python 环境：`fitness-agent`
- MediaPipe：`0.10.35`
- Pillow：`12.2.0`
- 模型：Google MediaPipe `pose_landmarker_full/float16`
- 本地路径：`data/models/pose_landmarker.task`
- 模型大小：`9,398,198` 字节
- SHA-256：`5134A3AAD27A58B93DA0088D431F366DA362B44E3CCFBE3462B3827A839011B1`

模型和样例图片分别位于 `data/models/` 与 `tmp/`，均已被 `.gitignore` 排除，不提交到 GitHub。

## 工具层真实推理结果

```text
图片解码：通过
图片尺寸：1000 x 667
姿态提取：通过
PoseSequence：T=1, J=33, C=3
source_type：image
pose_model：mediapipe_pose
joint_schema：mediapipe_33
coordinate_space：world
平均 visibility：0.9921567
```

## HTTP 接口结果

对真实模型执行：

```text
POST /motion/analyze-image
HTTP 200
```

响应确认包含：

- `frames=1`
- `joints=33`
- `pose_model=mediapipe_pose`
- `joint_schema=mediapipe_33`
- `confidence_summary.mean=0.9922`
- 单张图片只能用于静态姿态分析的边界提醒

## 结论与边界

Motion 图片最小链路已真实打通，原先“缺少 `pose_landmarker.task`”的本机阻塞已经解除。当前能力能够从单张真人图片提取三维世界坐标关键点并返回静态姿态摘要，但尚未实现动作专项关节规则、视频时序分析或完整动作质量判断。

下一步应进入视频抽帧与多帧 `PoseSequence(T=N)`，或先补深蹲单帧专项角度规则。
