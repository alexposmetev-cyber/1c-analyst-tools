@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0opencode.local.json" set "OPENCODE_CONFIG=%~dp0opencode.local.json"

if exist "%~dp0bin\opencode.exe" (
    "%~dp0bin\opencode.exe"
) else (
    echo bin\opencode.exe не найден. Запустите scripts\Update-OpenCode.cmd
    pause
    exit /b 1
)

endlocal
