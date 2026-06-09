@echo off
setlocal
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0agent\Bridge-Agent.ps1" -ConfigPath "%~dp0agent\bridge-agent.json"
