@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Setup-Mcp.ps1" %*
set ERR=%ERRORLEVEL%
if %ERR% neq 0 pause
exit /b %ERR%
