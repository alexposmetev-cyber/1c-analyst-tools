#Requires -Version 5.1
<#
.SYNOPSIS
    Podgotovka steka (Bridge, proksi 1bit AI) i zapusk OpenCode web v brauzere.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path $PSScriptRoot -Parent

$localConfig = Join-Path $ProjectRoot 'opencode.local.json'
if (Test-Path -LiteralPath $localConfig) {
    $env:OPENCODE_CONFIG = $localConfig
}

$bundledOpencode = Join-Path $ProjectRoot 'bin\opencode.exe'
if (Test-Path -LiteralPath $bundledOpencode) {
    $opencodePath = $bundledOpencode
}
else {
    $opencode = Get-Command opencode -ErrorAction SilentlyContinue
    if ($opencode) {
        $opencodePath = $opencode.Source
    }
    else {
        $npmOpencode = Join-Path $env:APPDATA 'npm\opencode.cmd'
        if (Test-Path -LiteralPath $npmOpencode) {
            $opencodePath = $npmOpencode
        }
    }
}

if (-not $opencodePath) {
    throw 'OpenCode ne naiden. Zapustite scripts\Update-OpenCode.cmd'
}

$bridgeScript = Join-Path $ProjectRoot 'scripts\Start-BridgeStack.ps1'
if (Test-Path -LiteralPath $bridgeScript) {
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $bridgeScript -Quiet | Out-Null
    }
    catch {
        Write-Warning "Bridge: $($_.Exception.Message)"
    }
}

$proxyScript = Join-Path $ProjectRoot 'scripts\Ensure-1bitaiProxy.ps1'
$proxyStarted = $false
if (Test-Path -LiteralPath $proxyScript) {
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $proxyScript
        $proxyStarted = $true
    }
    catch {
        Write-Host ''
        Write-Host 'PROKSI 1bit AI ne zapustilsya:' -ForegroundColor Yellow
        Write-Host $_.Exception.Message -ForegroundColor Yellow
        Write-Host 'Ukazhite API-klyuch kompanii:' -ForegroundColor Yellow
        Write-Host '  1) Peremennaya polzovatelya Windows ONEBITAI_API_KEY' -ForegroundColor Yellow
        Write-Host '  2) ili provider.1bitai.options.apiKey v opencode.local.json' -ForegroundColor Yellow
        Write-Host 'OpenCode otkroetsya, no modeli mogut ne rabotat.' -ForegroundColor Yellow
        Write-Host ''
    }
}

if ($proxyStarted) {
    $python = Join-Path $ProjectRoot 'mcp\.venv\Scripts\python.exe'
    $testProxy = Join-Path $ProjectRoot 'scripts\test_proxy.py'
    $localJson = Join-Path $ProjectRoot 'opencode.local.json'
    if ((Test-Path -LiteralPath $python) -and (Test-Path -LiteralPath $testProxy)) {
        if (-not $env:ONEBITAI_API_KEY -and (Test-Path -LiteralPath $localJson)) {
            try {
                $cfg = Get-Content -LiteralPath $localJson -Raw -Encoding UTF8 | ConvertFrom-Json
                $resolvedKey = [string]$cfg.provider.'1bitai'.options.apiKey
                if ($resolvedKey -and -not $resolvedKey.StartsWith('{env:')) {
                    $env:ONEBITAI_API_KEY = $resolvedKey
                }
            }
            catch {
                # test_proxy sam prochitaet klyuch pri neobhodimosti
            }
        }
        & $python $testProxy
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'PROVERKA PROKSI NE PROSHLA. Smotrite output\1bitai-proxy.err.log' -ForegroundColor Yellow
        }
    }
}

Set-Location $ProjectRoot

Write-Host 'Zapusk OpenCode (web)...' -ForegroundColor Cyan
Start-Process -FilePath $opencodePath -ArgumentList @('web') -WorkingDirectory $ProjectRoot | Out-Null
Write-Host 'Gotovo. Esli brauzer ne otkrylsya — otkroyte URL iz okna OpenCode ili http://127.0.0.1:<port>'
