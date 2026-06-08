#Requires -Version 5.1
<#
.SYNOPSIS
    Выгрузка конфигурации 1С в XML-файлы для анализа кода агентом.

.DESCRIPTION
    Обёртка над Get-1CData.ps1 -DumpConfig. Использует конфигуратор (DumpConfigToFiles).
    COM-коннектор код модулей не читает — только метаданные и данные.

.PARAMETER InfoBasePath
    Каталог файловой информационной базы.

.PARAMETER InfoBaseName
    Имя базы из ibases.v8i.

.PARAMETER Server
    Сервер 1С (серверная база).

.PARAMETER Ref
    Имя базы на сервере.

.PARAMETER User
    Пользователь 1С.

.PARAMETER Password
    Пароль.

.PARAMETER Mode
    Full — вся конфигурация (долго). Partial — выбранные объекты.

.PARAMETER Objects
    Список объектов через запятую для Partial, например: Документ.ЗаказКлиента,ОбщийМодуль.ОбщегоНазначения

.PARAMETER OutputPath
    Каталог выгрузки. По умолчанию — metadata/config-sources/{база}/

.EXAMPLE
    .\Dump-1CConfigToFiles.ps1 -InfoBaseName "DemoTrd" -User "Администратор" `
        -Mode Partial -Objects "Документ.ЗаказКлиента"

.EXAMPLE
    .\Dump-1CConfigToFiles.ps1 -InfoBasePath "C:\Users\me\Documents\1C\DemoTrd" -User "Администратор" `
        -Mode Full -OutputPath "D:\src\DemoTrd"
#>
[CmdletBinding()]
param(
    [string]$InfoBasePath,
    [string]$InfoBaseName,
    [string]$Server,
    [string]$Ref,
    [string]$User = '',
    [string]$Password = '',
    [ValidateSet('Full', 'Partial')]
    [string]$Mode = 'Partial',
    [string]$Objects = '',
    [string]$OutputPath = '',
    [string]$PlatformPath = '',
    [string]$Extension = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$getData = Join-Path $root 'Get-1CData.ps1'

if ($Mode -eq 'Partial' -and -not $Objects.Trim()) {
    throw 'Для Partial укажите -Objects (через запятую).'
}

$args = @(
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-File', $getData,
    '-DumpConfig',
    '-DumpMode', $Mode,
    '-AgentMode',
    '-Quiet'
)

if ($InfoBasePath) { $args += '-InfoBasePath', $InfoBasePath }
if ($InfoBaseName) { $args += '-InfoBaseName', $InfoBaseName }
if ($Server) { $args += '-Server', $Server }
if ($Ref) { $args += '-Ref', $Ref }
if ($User) { $args += '-User', $User }
if ($Password) { $args += '-Password', $Password }
if ($Objects) { $args += '-DumpObjects', $Objects }
if ($OutputPath) { $args += '-DumpOutputPath', $OutputPath }
if ($PlatformPath) { $args += '-PlatformPath', $PlatformPath }
if ($Extension) { $args += '-DumpExtension', $Extension }

& powershell.exe @args
