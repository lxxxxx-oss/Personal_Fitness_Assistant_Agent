# 后端端口启动记录

## 时间戳

2026-06-23

## 操作类型

运维脚本新增 / 服务启动

## 变更概述

为方便在 Windows 桌面环境中持久运行后端服务，新增启动脚本：

```text
scripts/run_backend.cmd
```

脚本行为：

- 切换到项目根目录。
- 创建 `logs/` 目录。
- 设置 `MCP_SERVER_COMMAND=mock`。
- 启动 FastAPI 后端：

```text
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- 日志输出到：

```text
logs/uvicorn.out.log
logs/uvicorn.err.log
```

## 启动结果

已通过独立本机窗口启动后端服务。

验证结果：

```text
GET http://127.0.0.1:8000/health -> {"status":"ok","version":"0.1.0"}
GET http://127.0.0.1:8000/ui -> 200
```

当前监听端口：

```text
127.0.0.1:8000
```

## 说明

Codex 工具命令中的后台子进程可能在命令结束后被清理，因此本次使用外部本机窗口保持服务运行。

如果需要停止服务，可以关闭启动脚本打开的 cmd 窗口，或执行：

```powershell
netstat -ano | Select-String ':8000'
taskkill /PID <pid> /F
```

## Next Steps

- 配置本地 `MODEL_PATH` 后，可以进一步体验 `/chat` 和 `/chat/stream`。
- 不依赖 LLM 的 `/health`、`/ui` 和 `/motion/analyze` 已可直接访问。
