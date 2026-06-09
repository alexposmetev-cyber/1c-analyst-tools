@echo off
setlocal
cd /d "%~dp0"

echo.
echo === 1C Analyst Tools: корпоративный SSL ===
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Apply-CorporateSsl.ps1" -Persist %*
if errorlevel 1 (
    echo.
    echo Ошибка настройки корпоративного SSL.
    pause
    exit /b 1
)

echo.
pause
endlocal
