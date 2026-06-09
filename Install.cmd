@echo off
setlocal
cd /d "%~dp0"

echo.
echo === 1C Analyst Tools — установка ===
echo.

REM UTF-8 BOM для PowerShell 5.1 + кириллица (после git clone / без BOM скрипт не парсится)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Fix-AllPs1Utf8Bom.ps1" >nul 2>nul

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
