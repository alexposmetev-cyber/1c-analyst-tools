#Requires -Version 5.1

<#

.SYNOPSIS

    Запуск OpenCode: Bridge + прокси 1bit AI + веб-интерфейс в браузере.

#>

Set-StrictMode -Version Latest

$ErrorActionPreference = 'Stop'



$launcher = Join-Path $PSScriptRoot 'scripts\Start-OpenCodeApp.ps1'

if (-not (Test-Path -LiteralPath $launcher)) {

    throw "Ne naiden: $launcher"

}



& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher

