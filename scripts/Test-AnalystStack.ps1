#Requires -Version 5.1
<#
.SYNOPSIS
    Smoke-тест MCP-слоя и Get-1CData на DemoTrd (без OpenCode).

.EXAMPLE
    .\scripts\Test-AnalystStack.ps1
#>
param(
    [string]$InfoBasePath = "C:\Users\aaposmetev\Documents\1C\DemoTrd",
    [string]$User = "Администратор",
    [string]$Password = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = Split-Path $PSScriptRoot -Parent
$GetData = Join-Path $Root 'Get-1CData.ps1'

Write-Host "1. ListInfoBases JSON..."
$list = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $GetData -ListInfoBases -OutputFormat Json
if (-not $list) { throw "ListInfoBases failed" }
Write-Host "   OK"

function Invoke-Get1CData {
    param([string[]]$ExtraArgs)
    $argList = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $GetData,
        '-InfoBasePath', $InfoBasePath,
        '-User', $User
    )
    if ($Password) {
        $argList += @('-Password', $Password)
    }
    $argList += $ExtraArgs
    & powershell.exe @argList
}

Write-Host "2. AgentMode query..."
$out = Invoke-Get1CData -ExtraArgs @('-AgentMode', '-Query', 'ВЫБРАТЬ ПЕРВЫЕ 3 Номер КАК N, Дата КАК D ИЗ Документ.ЗаказКлиента')
$parsed = $out | ConvertFrom-Json
if ($parsed.rowCount -lt 1) { throw "Expected rows, got: $out" }
Write-Host "   OK rows=$($parsed.rowCount)"

Write-Host "3. ReadOnly guard..."
$failed = $false
try {
    Invoke-Get1CData -ExtraArgs @('-ReadOnly', '-Query', 'УДАЛИТЬ ИЗ Справочник.Контрагенты') 2>&1 | Out-Null
}
catch { $failed = $true }
if (-not $failed) { throw "ReadOnly should reject non-SELECT" }
Write-Host "   OK"

Write-Host "4. MCP env + python import..."
$env:ONEC_IB_PATH = $InfoBasePath
$env:ONEC_USER = $User
$env:ONEC_PASSWORD = $Password
python -c "import mcp; print('mcp ok')" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "   SKIP: pip install -r mcp/requirements.txt" -ForegroundColor Yellow
}
else {
    Write-Host "   OK"
}

Write-Host ""
Write-Host "Stack test completed."
