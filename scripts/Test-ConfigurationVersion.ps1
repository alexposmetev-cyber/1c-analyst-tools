#Requires -Version 5.1
<#
.SYNOPSIS
    Проверка чтения имени и версии конфигурации через COM.
#>
param(
    [string]$InfoBasePath = "C:\Users\aaposmetev\Documents\1C\DemoTrd",
    [string]$User = "Администратор",
    [string]$Password = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = Split-Path $PSScriptRoot -Parent
. (Join-Path $Root 'Lib\1CComAccess.ps1')
. (Join-Path $Root 'Lib\1CPlatform.ps1')

$connection = Connect-1CInfobaseAuto -InfoBasePath $InfoBasePath -User $User -Password $Password
try {
    $metadata = Get-1CConnectionMetadata -Connection $connection
    $info = Get-1CConfigurationInfo -Connection $connection -Metadata $metadata -InfoBasePath $InfoBasePath
    [pscustomobject]@{
        configurationName = [string]$info.Name
        configurationSynonym = [string]$info.Synonym
        version = [string]$info.Version
        versionKnown = -not [string]::IsNullOrWhiteSpace([string]$info.Version)
    } | ConvertTo-Json -Compress
}
finally {
    if ($null -ne $connection) {
        try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($connection) } catch { }
    }
}
