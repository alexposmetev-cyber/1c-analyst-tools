#Requires -Version 5.1
<#
.SYNOPSIS
    Печатает приветствие и список функций аналитика 1С (для консоли при старте OpenCode).
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = Split-Path $PSScriptRoot -Parent
$Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $Python)) {
    Write-Host "MCP venv не найден. Запустите Setup-Mcp.ps1" -ForegroundColor Yellow
    exit 0
}

$code = @"
import sys
sys.path.insert(0, r'$($PSScriptRoot -replace "'", "''")')
from welcome import build_welcome_payload, format_welcome_text
from connection_session import load_session
from pathlib import Path
root = Path(r'$($Root -replace "'", "''")')
session = load_session(root)
payload = build_welcome_payload(root, session)
print(format_welcome_text(payload))
"@

$env:PYTHONIOENCODING = 'utf-8'
& $Python -c $code
