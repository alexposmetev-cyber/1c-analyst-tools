#Requires -Version 5.1
<#
.SYNOPSIS
    Скачивает OpenCode v1.16.2 в bin\opencode.exe.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$version = 'v1.16.2'
$zipUrl = "https://github.com/anomalyco/opencode/releases/download/$version/opencode-windows-x64.zip"
$zip = Join-Path $env:TEMP 'opencode-windows-x64.zip'
$extract = Join-Path $env:TEMP 'opencode-upgrade'
$binDir = Join-Path $PSScriptRoot '..\bin'
$target = Join-Path $binDir 'opencode.exe'
$projectRoot = Split-Path $PSScriptRoot -Parent

. (Join-Path $PSScriptRoot 'CorporateSsl.ps1')
Enable-CorporateSslProcess -ProjectRoot $projectRoot | Out-Null

New-Item -ItemType Directory -Force -Path $binDir | Out-Null
Write-Host "Скачивание $zipUrl ..."
Invoke-WebRequest -Uri $zipUrl -OutFile $zip -UseBasicParsing
if (Test-Path $extract) { Remove-Item $extract -Recurse -Force }
Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
Copy-Item (Join-Path $extract 'opencode.exe') $target -Force
$ver = & $target --version 2>&1 | Select-Object -Last 1
Write-Host "Готово: $target ($ver)"
