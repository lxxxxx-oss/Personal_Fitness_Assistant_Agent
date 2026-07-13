# Motion 子图优化路线与维护台账

本文档用于持续维护 Motion 子图的优化路线。每推进一步，都要记录“做到哪一步了、实际做法是什么、和预设路线是否有偏差、为什么偏差是合理的”。这样面试时可以清楚说明项目不是一次性 Demo，而是有阶段目标、边界意识和演进路径。

相关背景文档：

- [MOTION_MEDIA_PIPELINE_DESIGN.md](./MOTION_MEDIA_PIPELINE_DESIGN.md)
- [SUBGRAPH_OPTIMIZATION_GUIDE.md](../interview-archive/SUBGRAPH_OPTIMIZATION_GUIDE.md)

## 1. 当前总状态

截至 2026-07-07：

| 能力 | 当前状态 | 说明 |
|---|---|---|
| Motion 子图 | 已实现 | `think -> parse -> tool -> check` |
| `.npz` 姿态分析 | 已实现 | `/motion/analyze` 支持 `.npz` 上传 |
| 姿态归一化与相似度 | 已实现 | `normalize_pose`、FastDTW、cosine similarity、shape difference |
| PoseSequence 中间格式 | 已实现 | `app/tools/pose_sequence.py`，兼容 `.npz` metadata |
| 姿态估计适配器 | 已实现 | `app/tools/pose_estimator.py`，MediaPipe 可选依赖 |
| 图片静态姿态分析 | 已验证 | `/motion/analyze-image`，已使用真实 MediaPipe 模型完成单帧图片 -> PoseSequence 验收 |
| 视频姿态估计与相似度 | 已验证 | 视频 PoseSequence 可选择兼容标准动作，执行 FastDTW、余弦和 DTW 对齐逐关节平均距离；已知坐标空间不一致时拒绝 |
| 标准动作库工具链 | 已实现 | 标准视频可离线生成带 pose_model/joint_schema metadata 的 `.npz`；正式样本集待采集 |
| 动作专项规则 | 未实现 | 计划先从深蹲、硬拉、卧推等高频动作做 |
| Motion 评测集 | 未实现 | 计划覆盖姿态提取、相似度、低质量媒体降级 |
| 前端/小程序上传体验 | 代码已完成 | 图片/视频选择、预览、上传进度、标准动作选择和结果展示已接入；真机待验收 |

面试时可以准确表述为：

> 当前 Motion 已完成视频到 PoseSequence、同 schema 标准动作发现、髋中心归一化和多指标相似度链路。它能回答“和某个标准样本有多接近”，但动作周期切分、正式标准样本集和关节级专项纠错仍需补齐。

## 2. 优化路线总览

```text
Step 1  PoseSequence 中间格式
Step 2  姿态估计适配器
Step 3  图片静态姿态分析
Step 4  视频动作序列分析
Step 5  标准动作库
Step 6  动作专项质量规则
Step 7  Motion 评测集
Step 8  前端/小程序上传体验
```

一句话版本：

> Motion 的优化路线是先把 `.npz` 从用户输入降级为内部格式，再补 media-to-pose 适配层，用 MediaPipe 这类开源模型把图片/视频转成 PoseSequence；随后建设标准动作库、加入动作专项规则和评测集，最终形成从用户媒体输入到专业动作反馈的完整链路。

## 3. 分步路线与维护记录

### Step 1：定义统一姿态数据格式 `PoseSequence`

预设目标：

```text
keypoints: (T, J, C)
fps
source_type: image / video / npz
pose_model
joint_schema
confidence / visibility
metadata
```

预设做法：

- 新增统一数据结构或 schema 文档。
- 保留 `.npz` 作为内部持久化、调试、评测和标准动作库格式。
- 兼容当前 `motion_tool.load_npz_pose()` 的 `(T, J, 3)` 输入。

当前状态：已实现，已通过局部测试和全量回归。

实际做法记录：

- 新增 `app/tools/pose_sequence.py`，定义 `PoseSequence` dataclass。
- 新增 `validate_pose_sequence()`，校验 `keypoints: (T, J, C)`、数值类型、有限值、最小帧数、最小关键点数和可选 `confidence` 对齐关系。
- 新增 `pose_sequence_to_npz_payload()`，将 `PoseSequence` 序列化为稳定 `.npz` payload。
- 新增 `pose_sequence_from_npz()`，支持从 `.npz` 读取 `keypoints`、`pose`、`positions` 兼容 key，并解析 `fps`、`source_type`、`pose_model`、`joint_schema`、`confidence` 和 `meta_*` metadata。
- 更新 `app/tools/motion_tool.py`，让 `load_npz_pose()` 复用 `PoseSequence` schema，但保持旧行为：成功时仍返回 `(T, J, 3)` ndarray，避免破坏 `/motion/analyze` 和 Motion 子图。
- 更新 `app/tools/__init__.py`，导出 `PoseSequence` 和相关 helper。
- 新增 `tests/test_pose_sequence.py`，覆盖 schema 校验、metadata round-trip、legacy `.npz` key 兼容和 `(T,J,4)` 到分析层前三维兼容。

偏差说明：

- 预设路线只要求定义 `PoseSequence` 和 `.npz` metadata schema；实际实现时额外让 `load_npz_pose()` 复用该 schema。这个偏差是正向的，因为它把新格式真正接入了现有 Motion 分析入口，同时保持 API 返回结构不变。
- `PoseSequence` 允许 `C >= 2`，但当前 `motion_tool` 分析层仍要求至少前三维坐标；因此 `load_npz_pose()` 会通过 `analysis_keypoints()` 截取前三维。这样为后续 MediaPipe 的 visibility/confidence 预留空间，又不影响现有 `(T,J,3)` 算法。

### Step 2：接入开源姿态估计模型

预设目标：

```text
图片 / 视频 -> 人体关键点 -> PoseSequence
```

预设做法：

- 第一版优先接入 MediaPipe Pose。
- 新增 `app/tools/pose_estimator.py`。
- 对外输出统一 `PoseSequence`，不要让下游依赖 MediaPipe 的原始返回结构。
- 后续可替换 MoveNet、RTMPose、OpenPose 或 YOLO-Pose。
- 不从零训练模型，除非后续有标注数据、算力和明确精度目标。

当前状态：已实现适配器骨架，已通过局部测试。

实际做法记录：

- 新增 `app/tools/pose_estimator.py`。
- 新增 `validate_image_array()`，校验输入必须是 RGB 图像数组 `(H, W, 3)`。
- 新增 `estimate_pose_from_image()`，以 MediaPipe Pose 为第一版实现目标，把单张图片转换为 `PoseSequence`。
- MediaPipe 使用懒加载：未安装 `mediapipe` 时返回 `CONFIG_MISSING`，不会影响现有聊天、RAG、Router 或 `.npz` Motion 分析。
- 新增 `_extract_mediapipe_landmarks()`，将 MediaPipe 33 个 landmark 转成 `PoseSequence`，其中 keypoints 使用 `x/y/z`，visibility 写入 `confidence`。
- 更新 `app/tools/__init__.py`，导出 `estimate_pose_from_image()` 和 `validate_image_array()`。
- 新增 `tests/test_pose_estimator.py`，覆盖 RGB 图像校验、灰度图拒绝、MediaPipe 缺失降级和 landmark 到 `PoseSequence` 的转换。

偏差说明：

- 预设路线是“接入 MediaPipe Pose”。实际实现没有把 `mediapipe` 加成强依赖，也没有直接新增图片上传 API，而是先落地可选依赖适配器。这是为了不破坏当前项目运行和测试环境，同时先稳定工具边界。
- 当前函数接收的是 RGB `np.ndarray`，不直接负责文件读取和上传处理。图片文件解码和 HTTP 上传属于 Step 3 的接口层职责。

### Step 3：图片静态姿态分析

预设目标：

```text
图片 -> 单帧关键点 -> 关节角度 -> 静态姿态建议
```

预设做法：

- 新增或扩展媒体分析接口，优先支持 `.jpg`、`.jpeg`、`.png`。
- 单帧图片转换为 `PoseSequence(T=1)`。
- 输出静态姿态、关键关节角度、置信度提醒。
- 明确边界：图片不能判断动作节奏、完整轨迹和发力顺序。

当前状态：已实现图片上传入口，并已通过真实 MediaPipe 模型与 HTTP 接口验收。

实际做法记录：

- 新增 `/motion/analyze-image`。
- 新增 `MotionAnalyzeImageResponse`，返回文件名、source_type、frames、joints、pose_model、joint_schema、confidence_summary、warnings 和 message。
- 更新 `app/tools/pose_estimator.py`，新增 `decode_image_bytes_to_rgb()`，使用 Pillow 将 `.jpg`、`.jpeg`、`.png` 解码为 RGB numpy array。
- `/motion/analyze-image` 调用 `decode_image_bytes_to_rgb()` 和 `estimate_pose_from_image()`，将图片转为 `PoseSequence(T=1)`。
- 返回固定 warning：单张图片只能分析静态姿态，不能判断动作节奏、轨迹或发力顺序。
- 当关键点平均置信度低于 0.5 时，额外提示更换清晰、无遮挡图片。
- 更新 Web UI：在 `/ui` 输入栏新增图片上传按钮，用户选择图片后调用 `/motion/analyze-image` 并在消息区展示静态姿态摘要。
- 新增 `tests/test_api.py::TestMotionAnalyzeImageEndpoint`，覆盖图片上传成功和非图片后缀拒绝。
- 更新 `tests/test_pose_estimator.py`，覆盖图片字节解码和不支持后缀拒绝。

偏差说明：

- 预设目标中提到“关节角度”。本次先完成图片上传、解码、姿态提取和置信度摘要，没有加入具体动作的关节角度规则。原因是关节角度需要按动作类型定义关键关节映射，属于 Step 6“动作专项质量规则”的一部分；当前先保证媒体入口和 PoseSequence 链路稳定。
- 当前图片接口依赖 MediaPipe 可用性；项目仍没有把 `mediapipe` 写成强依赖，所以未安装时会返回 `503 CONFIG_MISSING` 对应的错误说明。
- 2026-06-26 手工上传图片时发现本机 `mediapipe==0.10.35` 不再暴露旧版 `mp.solutions` API。已将适配器改为：显式 import `mediapipe.solutions.pose` / `mediapipe.python.solutions.pose`，只有旧版模块可导入时才走旧 API；否则走 MediaPipe Tasks API，避免直接访问 `mp.solutions` 属性。Tasks API 需要本地 `pose_landmarker.task` 模型文件，可通过 `MEDIAPIPE_POSE_MODEL_PATH` 配置，默认路径为 `data/models/pose_landmarker.task`。
- 2026-07-02 下载 Google 官方 `pose_landmarker_full/float16` 模型到本地忽略目录 `data/models/pose_landmarker.task`，使用官方人体样例图完成真实推理：输出 `PoseSequence(T=1, J=33, C=3)`，平均 visibility 为 `0.9922`；随后通过 `/motion/analyze-image` 完成 HTTP 200 验收。模型文件和测试图片均由 `.gitignore` 排除，不提交到仓库。

### Step 4：视频动作序列分析

预设目标：

```text
视频 -> 抽帧 -> 多帧关键点 -> PoseSequence(T=N)
```

预设做法：

- 支持短视频上传。
- 控制视频时长、文件大小和抽帧频率。
- 对关键点做平滑、缺失帧处理和置信度过滤。
- 复用现有 Motion 算法：

```text
normalize_pose
  -> FastDTW 对齐
  -> cosine similarity
  -> shape difference
  -> 动作评价
```

当前状态：视频姿态提取与可选标准样本相似度已实现并通过真实链路验收；关键点平滑、缺失帧插值、动作周期切分和专项动作评分尚未实现。

实际做法记录：

- 新增 `estimate_pose_from_video_path()`，使用 OpenCV 读取视频，并通过 MediaPipe `VIDEO` 模式按时间戳提取关键点。
- 默认目标采样率约 10 FPS，最多处理 300 个采样帧；上传限制为 30 MB。
- 未检测到人体的帧会跳过，输出记录 `sampled_frames`、`valid_frames` 和 `valid_frame_ratio`。
- 新增 `/motion/analyze-video`，支持 `.mp4`、`.mov`、`.avi`，请求结束后删除临时文件。
- 使用真实 MediaPipe 模型和短 MP4 完成 HTTP 200 验收，生成 `PoseSequence(T=15, J=33, C=3)`，有效帧率为 100%。
- 新增 `compute_pose_sequence_similarity()`：要求用户序列与参考序列的 `pose_model`、`joint_schema` 一致，已知 `coordinate_space` 不一致时拒绝；MediaPipe 33 点使用 23/24 号髋关节中点做中心化。
- 2026-07-08 修正 `shape_difference`：旧实现只比较每帧姿态矩阵的整体范数，可能掩盖关节结构变化；新实现复用 FastDTW 对齐路径，计算对应帧逐关节欧氏距离的全局均值。该值仍是原型阈值，不提供关节级定位。
- `/motion/analyze-video` 增加可选 `reference_name`，兼容时返回 FastDTW、余弦相似度、形状差异和整体结论；不兼容时返回 422。
- 同一真实视频先构建参考再上传比较，得到 DTW `0.0`、余弦 `1.0`、形状差异 `0.0`，证明 MediaPipe -> 标准库 -> 相似度公开接口闭环成立。

偏差说明：

- 本轮接入的是“整段视频与标准样本的通用相似度”，没有提前宣称已经完成单次动作周期识别或关节级纠错。相似度表达样本接近程度，不直接等价于专业动作质量。

### Step 5：建设标准动作库

预设目标：

```text
标准动作视频
  -> 同一个姿态估计模型
  -> 标准 PoseSequence
  -> 保存为 data/motions/*.npz
```

预设做法：

- 不手写 `.npz`。
- 用同一姿态估计模型处理用户视频和标准视频，保证关键点 schema 一致。
- 第一批动作优先覆盖：深蹲、硬拉、卧推、俯卧撑、平板支撑。
- 每个动作记录来源、拍摄角度、帧率、pose_model、joint_schema。

当前状态：构建工具和 schema 门禁已实现；正式标准动作样本集未完成。

实际做法记录：

- 新增 `scripts/build_motion_reference.py`，用同一个 `estimate_pose_from_video_path()` 把标准视频生成稳定 PoseSequence `.npz`。
- 脚本写入 `pose_model`、`joint_schema`、fps、confidence 和来源 metadata；默认拒绝覆盖，参考名称禁止路径字符。
- 新增 `GET /motion/references`，列出参考动作并标记是否兼容当前 MediaPipe 视频链路。
- 早期随机 `data/motions/squat.npz` 为 17 关节 unknown schema 占位数据，接口会标记不兼容，不用于视频评分。

偏差说明：

- 本阶段先完成“标准库生产工具 + 一致性门禁”，没有提交伪造的深蹲标准样本。正式样本需要明确来源、拍摄视角和教练确认后再加入。

### Step 6：增加动作专项质量规则

预设目标：

让反馈不只停留在“相似度 0.82”，而是能说出具体动作问题。

预设做法：

| 动作 | 规则方向 |
|---|---|
| 深蹲 | 膝角、髋角、躯干前倾、膝盖内扣、下蹲深度 |
| 硬拉 | 背部中立、髋膝协同、起始姿态、杠铃轨迹 |
| 卧推 | 肘部角度、肩部稳定、左右对称、动作幅度 |
| 俯卧撑 | 身体直线、肘部角度、肩胛稳定、下放深度 |
| 平板支撑 | 骨盆位置、躯干直线、肩髋踝对齐 |

当前状态：未实现。

实际做法记录：

- 暂无。

偏差说明：

- 暂无。

### Step 7：建立 Motion 评测集

预设目标：

评测重点不是 LLM 文案，而是动作分析链路是否稳定、可解释、能正确降级。

预设做法：

- 姿态估计成功率。
- 关键点置信度和缺失率。
- 视频关键点连续性。
- 标准动作相似度稳定性。
- 低质量图片/视频是否正确降级。
- 动作专项规则是否命中预期问题。

当前状态：未实现。

实际做法记录：

- 暂无。

偏差说明：

- 暂无。

### Step 8：接入前端/小程序上传体验

预设目标：

```text
用户上传图片/视频
  -> 后端分析
  -> 返回关键指标 + 中文解释
  -> 前端展示动作建议
```

预设做法：

- Web UI 和小程序端支持选择图片/视频。
- 上传前做大小、类型、时长提示。
- 返回结果区分：姿态提取状态、指标结果、动作建议、风险提醒。
- 对低置信度媒体给出重新拍摄建议。

当前状态：小程序代码已实现，微信开发者工具和真机待验收。

实际做法记录：

- 小程序支持图片/视频选择、本地预览、10MB/30MB 校验和上传进度。
- 视频上传前调用 `/motion/references`；有兼容标准时让用户选择仅提取或执行相似度，无兼容参考时安全退回姿态提取。
- 结果区展示有效帧、抽样帧、FPS、置信度，以及可选 DTW/余弦/形状差异和边界 warning。

偏差说明：

- 暂无。

## 4. 维护规则

后续每推进 Motion 的一个步骤，都要更新本文档对应 Step 的三项内容：

- 当前状态：`未实现`、`设计中`、`开发中`、`已实现`、`已验证`、`暂缓`。
- 实际做法记录：写清楚改了哪些文件、接口或数据。
- 偏差说明：如果实际做法和预设路线不同，说明为什么改变，以及是否影响面试表述。

如果新增接口，还要同步更新：

- `docs/02_接口说明.md`
- `docs/01_项目总览.md`
- `docs/progress/`

如果新增后端用户可见能力，还要同步检查：

- `app/static/index.html`
- `docs/miniprogram/`

其中 Web UI 是本项目当前最直接的手工演示入口，后续 Motion、Router、Search、Diet、MCP 的用户可见能力都应优先确认 `/ui` 是否需要新增控件、状态展示或错误提示。

如果新增测试或执行测试，还要同步更新：

- `docs/tests/`

## 5. 当前下一步

Step 1-5 的核心工具链和 Step 8 端侧代码已完成，当前下一步是把通用相似度升级为动作质量闭环：

1. 对视频关键点做基础平滑和缺失帧处理。
2. 增加单次深蹲动作周期切分。
3. 采集与 `mediapipe_33` 一致、同视角并经教练确认的正式标准动作样本。
4. 为深蹲等动作增加关节角、幅度、对称性和阶段级规则。
