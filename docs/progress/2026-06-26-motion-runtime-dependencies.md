# 2026-06-26 Motion 运行依赖整理

## 操作类型

配置整理 / 文档维护。

## 背景

手工测试 Web UI 图片上传时，`/motion/analyze-image` 已经成功进入 MediaPipe Tasks 路径，但返回：

```text
MediaPipe Pose Landmarker model file is missing.
```

这说明 UI 上传和后端接口链路已打通，当前阻塞点是 Motion 图片姿态估计的本地运行资产和可选依赖没有准备完整。

## 本次变更

更新依赖文件：

- `requirements.txt`
- `requirements-motion.txt`

更新文档：

- `.codex/COMMANDS.md`
- `docs/README.md`
- `docs/progress/2026-06-26-motion-runtime-dependencies.md`

## 实现内容

- 将 `requirements.txt` 整理为基础依赖，覆盖后端、LangGraph、RAG、搜索、MCP、`.npz` Motion 分析和测试。
- 新增 `requirements-motion.txt`，用于安装 Motion 图片姿态估计所需的可选依赖 `mediapipe`。
- 文档中补充说明：真实图片关键点提取还需要本地 `pose_landmarker.task` 模型文件。
- 明确 `data/models/` 和 `*.task` 不提交到 Git，两台电脑需要分别准备模型文件。

## 影响范围

- 不改变任何 API 行为。
- 不改变测试逻辑。
- 不影响普通聊天、RAG、Router、Search、MCP 或 `.npz` Motion 分析。
- `/motion/analyze-image` 的真实 MediaPipe 推理仍需要安装 `requirements-motion.txt` 并准备 `pose_landmarker.task`。

## Next Steps

1. 在当前 conda 环境执行 `pip install -r requirements-motion.txt`。
2. 下载 `pose_landmarker.task` 到 `data/models/pose_landmarker.task`，或设置 `MEDIAPIPE_POSE_MODEL_PATH`。
3. 重启后端后，通过 Web UI 重新上传图片验证真实关键点提取。

## Conda 启动链路记录

基础启动：

```powershell
cd D:\Users\Agent\Personal_Fitness_Assistant_Agent
conda activate fitness-agent
pip install -r requirements.txt
$env:MCP_SERVER_COMMAND="mock"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Motion 图片姿态分析准备：

```powershell
pip install -r requirements-motion.txt
New-Item -ItemType Directory -Force data\models
curl.exe -L -o data\models\pose_landmarker.task https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task
```

打开 Web UI：

```text
http://127.0.0.1:8000/ui
```
