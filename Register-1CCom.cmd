@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Register-1CCom.ps1" %*
set ERR=%ERRORLEVEL%
if %ERR% neq 0 (
    echo.
    echo Exit code: %ERR%
    pause
)
exit /b %ERR%
