#Requires -Version 5.1
<#
.SYNOPSIS
    Однократная регистрация COM-коннектора 1С (comcntr.dll).

.EXAMPLE
    .\Register-1CCom.ps1

.EXAMPLE
    .\Register-1CCom.ps1 -PlatformPath "C:\Users\aaposmetev\AppData\Local\Programs\1cv8_x64\8.3.27.2130\bin"

.EXAMPLE
    Register-1CCom.cmd

.NOTES
    Регистрация comcntr.dll требует прав администратора Windows.
    Пользователь без админа получит текст заявки для IT.
    Из PowerShell: .\Register-1CCom.ps1
    Из cmd: Register-1CCom.cmd
#>
param(
    [string]$PlatformPath,
    [switch]$Silent
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Lib\1CPlatform.ps1')

Register-1CComConnectors -PlatformPath $PlatformPath -Elevate -Silent:$Silent
