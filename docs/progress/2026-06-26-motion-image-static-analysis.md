# 2026-06-26 Motion Step 3：图片静态姿态分析入口

## 操作类型

功能新增 / API 新增 / 测试新增 / 文档维护。

## 背景

Motion Roadmap 的第三步是让普通用户可以上传图片，而不是只接触 `.npz`。本阶段目标是完成单张图片到 `PoseSequence(T=1)` 的静态姿态入口，并明确单张图片不能判断完整动作节奏、轨迹或发力顺序。

## 本次变更

新增接口：

- `POST /motion/analyze-image`

更新代码：

- `app/main.py`
- `app/tools/pose_estimator.py`
- `app/tools/__init__.py`
- `requirements.txt`

更新测试：

- `tests/test_pose_estimator.py`
- `tests/test_api.py`

更新文档：

- `docs/API.md`
- `docs/README.md`
- `docs/interview/PROJECT_INTERVIEW_GUIDE.md`
- `docs/interview/SUBGRAPH_OPTIMIZATION_GUIDE.md`
- `docs/interview/motion/MOTION_MEDIA_PIPELINE_DESIGN.md`
- `docs/interview/motion/MOTION_OPTIMIZATION_ROADMAP.md`
- `docs/tests/2026-06-26-motion-image-static-analysis.md`

## 实现内容

新增 `decode_image_bytes_to_rgb()`：

- 支持 `.jpg`、`.jpeg`、`.png`。
- 使用 Pillow 解码图片为 RGB numpy array。
- 限制默认最大图片大小为 10 MB。
- 文件为空、后缀不支持、图片无法解码时返回 `INVALID_PARAM`。
- Pillow 缺失时返回 `CONFIG_MISSING`。

新增 `/motion/analyze-image`：

```text
图片文件
  -> decode_image_bytes_to_rgb()
  -> estimate_pose_from_image()
  -> PoseSequence(T=1)
  -> 静态姿态摘要
```

响应包含：

- `filename`
- `source_type`
- `frames`
- `joints`
- `pose_model`
- `joint_schema`
- `confidence_summary`
- `warnings`
- `message`

## 与预设路线的差异

预设路线提到“输出静态姿态、关键关节角度和低置信度提醒”。

本次实现了图片上传、解码、姿态提取、置信度摘要和静态分析 warning，但没有实现动作专项关节角度规则。原因是关节角度需要按具体动作定义关键关节映射，例如深蹲、硬拉、卧推各不相同，更适合放到 Step 6“动作专项质量规则”中实现。

## 工具/接口规范检查

- 职责清晰：`/motion/analyze-image` 只做图片单帧姿态提取和摘要，不做视频时序分析。
- 输入清晰：multipart 上传 `file`，支持 `.jpg`、`.jpeg`、`.png`。
- 输出清晰：返回姿态模型、关键点 schema、帧数、关键点数、置信度摘要和 warning。
- 权限清晰：只读取上传文件内容，不写磁盘，不访问网络。
- 错误可处理：无效图片返回 422，Pillow 或 MediaPipe 缺失返回 503。

## 测试结果

局部测试：

```bash
pytest tests/test_pose_estimator.py tests/test_pose_sequence.py tests/test_api.py::TestMotionAnalyzeImageEndpoint -q
```

结果：

```text
13 passed, 1 warning
```

全量回归：

```bash
pytest -q
```

结果：

```text
91 passed, 1 skipped, 1 warning
```

## Next Steps

1. 进入 Step 4：设计视频上传、抽帧和 `PoseSequence(T=N)` 生成。
2. 保持图片接口只做静态姿态摘要，不把它包装成完整动作质量判断。
3. 后续在 Step 6 为深蹲、硬拉、卧推等动作增加专项关节角度规则。
