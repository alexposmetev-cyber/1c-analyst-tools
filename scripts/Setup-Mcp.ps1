#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = Split-Path $PSScriptRoot -Parent
$Req = Join-Path $Root 'mcp\requirements.txt'
$Venv = Join-Path $Root 'mcp\.venv'

Write-Host "Creating venv: $Venv"
python -m venv $Venv

$pip = Join-Path $Venv 'Scripts\pip.exe'
& $pip install --upgrade pip
& $pip install -r $Req

$fixBom = Join-Path $Root 'scripts\Fix-AllPs1Utf8Bom.ps1'
if (Test-Path -LiteralPath $fixBom) {
    Write-Host ""
    Write-Host "Ensuring UTF-8 BOM on PowerShell scripts..."
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $fixBom
}

Write-Host ""
Write-Host "Done. For OpenCode set in .opencode/opencode.json:"
Write-Host '  "command": ["mcp/.venv/Scripts/python.exe", "mcp/server.py"]'
