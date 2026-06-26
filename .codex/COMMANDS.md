# 常用命令参考

这些命令来自原 Claude 本地权限配置，迁移后作为 Codex 运维和验证参考。是否执行仍受当前 Codex 运行环境权限控制。

## 依赖

```bash
pip install -r requirements.txt
pip install pytest pytest-asyncio
```

## 后端服务

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 健康检查和接口验证

```bash
curl -s http://127.0.0.1:8000/health
curl -s -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"u1\",\"message\":\"你好\"}"
```

## 测试

```bash
python -m pytest tests/ -q
python -m pytest tests/ -v --tb=short
python -m pytest tests/test_router.py tests/test_api.py tests/test_integration.py -v --tb=short -q
python -m pytest tests/test_motion_tool.py -v
python -m pytest tests/test_mcp_client.py -v
python -m pytest tests/test_retriever.py -v
python -m pytest tests/test_sliding_window.py -v
```

## 手工验证

```bash
python tests/manual_smoke.py
python tests/manual_level2.py
python tests/manual_level3.py
```

## MCP 检查

```bash
npm --version
npm install -g howtocook-mcp
where howtocook-mcp
howtocook-mcp
```

## Windows 进程排查

```powershell
tasklist
netstat -ano
taskkill /PID <pid> /F
```
