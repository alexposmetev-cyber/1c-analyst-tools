@echo off
setlocal
cd /d "%~dp0.."
set "VENV=%~dp0..\mcp\.venv\Scripts\python.exe"
if not exist "%VENV%" (
  echo MCP venv не найден. Запустите Install.cmd или scripts\Setup-Mcp.ps1
  exit /b 1
)
"%VENV%" -m pip install -q -r "%~dp0orchestrator\requirements.txt"
echo Orchestrator: http://127.0.0.1:8787
cd /d "%~dp0orchestrator"
"%VENV%" -m uvicorn app:app --host 127.0.0.1 --port 8787
