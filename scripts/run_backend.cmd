@echo off
cd /d "%~dp0.."
if not exist logs mkdir logs
set MCP_SERVER_COMMAND=mock
set LLM_MOCK=1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 1>logs\uvicorn.out.log 2>logs\uvicorn.err.log
