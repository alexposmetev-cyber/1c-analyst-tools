#Requires -Version 5.1
<#
.SYNOPSIS
    Включает обход корпоративного SSL для текущего процесса и .onec-web.json.

.PARAMETER Persist
    Записать переменные окружения в профиль пользователя Windows.

.PARAMETER Disable
    Отключить профиль: verify_ssl=true и удалить user env.

.EXAMPLE
    .\scripts\Apply-CorporateSsl.ps1 -Persist
#>
[CmdletBinding()]
param(
    [switch]$Persist,
    [switch]$Disable
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path $PSScriptRoot -Parent
. (Join-Path $PSScriptRoot 'CorporateSsl.ps1')

if ($Disable) {
    Disable-CorporateSslUser -ProjectRoot $ProjectRoot
    Ensure-OneCWebConfigForCorporateSsl -ProjectRoot $ProjectRoot -VerifySsl $true
    Write-Host 'Корпоративный SSL отключён (verify_ssl=true, user env удалены).'
    exit 0
}

$ok = Install-CorporateSslProfile -ProjectRoot $ProjectRoot -PersistUserEnv:$Persist
if (-not $ok) {
    exit 1
}

if ($Persist) {
    Write-Host 'Переменные ONEC_WEB_VERIFY_SSL / ONEBITAI_VERIFY_SSL сохранены для пользователя Windows.'
}
