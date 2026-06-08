@echo off
setlocal
cd /d "%~dp0.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Fix-AllPs1Utf8Bom.ps1" %*
set ERR=%ERRORLEVEL%
if %ERR% neq 0 (
    echo.
    echo Exit code: %ERR%
    pause
)
exit /b %ERR%
