#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = Split-Path $PSScriptRoot -Parent
$Python = Join-Path $Root 'mcp\.venv\Scripts\python.exe'
$McpDir = Join-Path $Root 'mcp'
$Probe = Join-Path $McpDir '_import_probe.py'

Write-Host '=== onec-data MCP ===' -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath $Python)) {
    Write-Host 'FAIL: no venv python. Run scripts\Setup-Mcp.ps1' -ForegroundColor Red
    exit 1
}

$ver = & $Python --version 2>&1
Write-Host "OK: $ver"

if (-not (Test-Path -LiteralPath $Probe)) {
    Write-Host "FAIL: probe script not found: $Probe" -ForegroundColor Red
    exit 1
}

Push-Location $McpDir
try {
    $sec = & $Python $Probe 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'FAIL import server.py' -ForegroundColor Red
        Write-Host $sec
        exit 1
    }
    Write-Host "OK: import server.py $($sec.Trim())s"
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host '=== COM / 1cestart ===' -ForegroundColor Cyan

. (Join-Path $Root 'Lib\1CPlatform.ps1')

foreach ($progId in @('V83.COMConnector', 'V85.COMConnector')) {
    $ok = Test-1CComConnectorRegistered -ProgId $progId
    $label = if ($ok) { 'OK' } else { 'NOT REGISTERED' }
    $color = if ($ok) { 'Green' } else { 'Red' }
    Write-Host "$progId : $label" -ForegroundColor $color
}

$installed = Get-1CInstalledLocationFromCfg
if ($installed) {
    Write-Host "InstalledLocation: $installed" -ForegroundColor Green
}
else {
    Write-Host 'InstalledLocation: NOT FOUND in 1cestart.cfg' -ForegroundColor Yellow
    Write-Host '  Hint: launch 1C once or set path in Register-1CCom.cmd -PlatformPath'
}

try {
    $candidates = Get-1CPlatformConnectCandidates
    Write-Host "Platform bins found: $($candidates.Count)"
    foreach ($c in $candidates) {
        Write-Host "  $($c.ProgId) $($c.Version) -> $($c.BinPath)"
    }
}
catch {
    Write-Host "Platform search FAIL: $($_.Exception.Message)" -ForegroundColor Red
}

$pwsh = Get-Command pwsh -ErrorAction SilentlyContinue
if ($pwsh) {
    Write-Host "PowerShell: $($pwsh.Source) (UTF-8 without BOM OK)" -ForegroundColor Green
}
else {
    Write-Host 'PowerShell: powershell.exe 5.1 ( .ps1 need UTF-8 BOM )' -ForegroundColor Yellow
    Write-Host '  Fix: scripts\Fix-AllPs1Utf8Bom.cmd'
}

Write-Host ''
Write-Host '=== Next steps ===' -ForegroundColor Cyan
Write-Host '1. If COM NOT REGISTERED -> admin Windows required (IT: Register-1CCom.cmd or regsvr32). No admin -> offline/research only.'
Write-Host '2. Cursor: Settings - MCP - onec-data - Restart'
Write-Host '3. MCP tools: onec_ping, onec_com_status, onec_connect (no refresh_metadata=true)'
Write-Host '4. First connect may take 30-60 seconds'
