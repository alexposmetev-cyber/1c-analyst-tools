#Requires -Version 5.1
<#
.SYNOPSIS
    Запуск OpenCode с конфигом проекта (локальная LLM).
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = $PSScriptRoot

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
    if (-not $opencode) {
        $npmOpencode = Join-Path $env:APPDATA 'npm\opencode.cmd'
        if (Test-Path -LiteralPath $npmOpencode) {
            $opencodePath = $npmOpencode
        }
    }
    else {
        $opencodePath = $opencode.Source
    }
}

if (-not $opencodePath) {
    throw "OpenCode не найден. Запустите scripts\Update-OpenCode.ps1 или установите opencode-ai."
}

Set-Location $ProjectRoot
& $opencodePath
