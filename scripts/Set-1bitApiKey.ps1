#Requires -Version 5.1
<#
.SYNOPSIS
    Сохраняет API-ключ 1bit AI в переменную пользователя Windows ONEBITAI_API_KEY.
#>
[CmdletBinding()]
param(
    [Parameter()]
    [string]$ApiKey
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $ApiKey) {
    $secure = Read-Host 'API-klyuch 1bit AI (ne otobrazhaetsya)' -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $ApiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

$ApiKey = $ApiKey.Trim()
if (-not $ApiKey) {
    throw 'Pustoj API-klyuch.'
}

[Environment]::SetEnvironmentVariable('ONEBITAI_API_KEY', $ApiKey, 'User')
$env:ONEBITAI_API_KEY = $ApiKey

Write-Host 'OK: ONEBITAI_API_KEY sohranen dlya tekushchego polzovatelya Windows.'
Write-Host 'Perezapustite Start-OpenCode.cmd (novoe okno cmd posle ustanovki peremennoj).'
