@echo off
setlocal
cd /d "%~dp0"

echo.
echo === 1C Analyst Tools — установка ===
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Install-1CAnalystStack.ps1" %*
if errorlevel 1 (
    echo.
    echo Установка завершилась с ошибкой.
    pause
    exit /b 1
)

echo.
pause
endlocal
