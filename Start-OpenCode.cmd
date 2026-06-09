@echo off
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-BridgeStack.ps1" -Quiet

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-OpenCodeApp.ps1"