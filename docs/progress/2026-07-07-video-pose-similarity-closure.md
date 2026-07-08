# Motion 视频 PoseSequence 相似度闭环

## 阶段目标

把真实视频生成的 PoseSequence 接入现有归一化、FastDTW、余弦相似度和形状差异算法，并确保不同姿态模型或关节 schema 不会被强行比较。

## 已完成内容

- 新增 `load_npz_pose_sequence()`，加载标准动作时保留 `pose_model`、`joint_schema`、fps、confidence 和 metadata。
- 新增 `compute_pose_sequence_similarity()`，只允许模型和 schema 一致的 PoseSequence 比较。
- MediaPipe 33 点序列使用 23/24 号髋关节中点中心化，再做尺度归一化。
- `compute_similarity()` 增加关节数和坐标维度一致性校验，避免底层 FastDTW 抛出难理解异常。
- `/motion/analyze-video` 增加可选 `reference_name`；兼容时返回三项指标、标签和整体结论。
- 新增 `GET /motion/references`，公开参考动作 metadata 和视频兼容状态。
- 新增 `scripts/build_motion_reference.py`，从标准视频离线生成同 MediaPipe schema 的参考 `.npz`。
- 小程序上传视频前发现兼容参考；用户可选择仅提取姿态或执行标准动作比较。

## 重要问题与处理

仓库原有 `data/motions/squat.npz` 是早期随机生成的 `12×17×3` legacy 占位数据，没有 pose model 和 joint schema。它不能和 MediaPipe 33 点视频产生有意义的比较。本阶段没有做 33→17 的猜测映射，而是把它标记为不兼容并返回明确 422。

## 接口设计检查

- 职责：PoseSequence 比较只负责同 schema 时序相似度，不宣称关节级专业诊断。
- 输入：用户视频、可选标准动作名称；标准动作只能从配置目录按白名单名称查找。
- 输出：稳定返回 reference、metrics、warning 和执行模式。
- 权限：构建脚本只写用户指定的标准库目录，名称禁止路径字符，默认拒绝覆盖。
- 错误处理：参考不存在返回 404；模型/schema 不兼容返回 422；不传参考安全退回姿态提取。

## 当前验证

- Motion、参考构建器和视频 API 定向测试：`20 passed, 1 warning`。
- 全量自动化回归：`139 passed, 2 skipped, 1 warning`。
- 真实标准构建：真实短视频生成 `15×33×3`、`mediapipe_pose/mediapipe_33` 参考。
- 真实公开接口比较：HTTP 200，DTW `0.0`、余弦 `1.0`、形状差异 `0.0`，执行模式 `mediapipe_video_similarity`。

## 如何解释真实冒烟

同一视频生成参考并再次比较得到满分，证明媒体输入、标准库序列化、schema 门禁、归一化和相似度算法接线正确。它不证明系统能判断任意深蹲是否标准，也不是准确率评测。

## 下一步

- 用明确来源、同视角、经教练确认的视频建立正式深蹲等参考样本。
- 增加关键点平滑和单次动作周期切分。
- 加入膝角、髋角、躯干倾斜、对称性和动作幅度等专项规则。
