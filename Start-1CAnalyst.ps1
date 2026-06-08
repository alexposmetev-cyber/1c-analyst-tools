#Requires -Version 5.1
<#
.SYNOPSIS
    Launcher для 1C Analyst — ввод подключения и запуск OpenCode с агентом 1c-analyst.

.EXAMPLE
    .\Start-1CAnalyst.ps1
#>
[CmdletBinding()]
param(
    [string]$InfoBasePath,
    [string]$Server,
    [string]$Ref,
    [string]$User,
    [string]$Password,
    [string]$Problem,
    [switch]$SkipOpenCode
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = $PSScriptRoot
$GetDataScript = Join-Path $ProjectRoot 'Get-1CData.ps1'
$RegisterComScript = Join-Path $ProjectRoot 'Register-1CCom.ps1'

. (Join-Path $ProjectRoot 'Lib\1CInfoBase.ps1')

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Read-SecurePasswordPlain {
    $secure = Read-Host "Пароль 1С (Enter если пустой)" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

function Get-OpenCodeCommand {
    $bundledOpencode = Join-Path $ProjectRoot 'bin\opencode.exe'
    if (Test-Path -LiteralPath $bundledOpencode) {
        return $bundledOpencode
    }

    $candidates = @('opencode', 'opencode.exe')
    foreach ($name in $candidates) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            return $cmd.Source
        }
    }

    $npmOpencode = Join-Path $env:APPDATA 'npm\opencode.cmd'
    if (Test-Path -LiteralPath $npmOpencode) {
        return $npmOpencode
    }

    return $null
}

function Import-InfoBaseList {
    return Get-1CInfoBaseList
}

function Select-InfoBase {
    param([string]$PresetPath)

    if ($PresetPath) {
        return [PSCustomObject]@{
            InfoBasePath = $PresetPath
            Server = $null
            Ref = $null
        }
    }

    Write-Step "Выбор информационной базы"
    $bases = @(Import-InfoBaseList)
    $baseCount = Get-1CCollectionCount -Value $bases

    if ($baseCount -gt 0) {
        Write-Host "Базы из ibases.v8i:"
        for ($i = 0; $i -lt $baseCount; $i++) {
            $displayName = Get-1CInfoBaseProperty -Item $bases[$i] -Names @('Name', 'name')
            Write-Host "  [$($i + 1)] $displayName"
        }
        Write-Host "  [0] Ввести путь вручную"
        $choice = Read-Host "Номер базы"
        if ($choice -match '^\d+$' -and [int]$choice -ge 1 -and [int]$choice -le $baseCount) {
            $selected = $bases[[int]$choice - 1]
            $connect = Get-1CInfoBaseProperty -Item $selected -Names @('Connect', 'connect')
            if ($connect -match 'File="([^"]+)"') {
                return [PSCustomObject]@{
                    InfoBasePath = $Matches[1]
                    Server = $null
                    Ref = $null
                }
            }
            if ($connect -match 'Srvr="([^"]+)"') { $srv = $Matches[1] } else { $srv = $null }
            if ($connect -match 'Ref="([^"]+)"') { $refName = $Matches[1] } else { $refName = $null }
            return [PSCustomObject]@{
                InfoBasePath = $null
                Server = $srv
                Ref = $refName
            }
        }
    }

    $manualPath = Read-Host "Путь к каталогу файловой базы"
    if (-not $manualPath) {
        throw "Путь к базе не указан."
    }
    return [PSCustomObject]@{
        InfoBasePath = $manualPath.Trim('"')
        Server = $null
        Ref = $null
    }
}

function Test-ComRegistered {
    return $null -ne [Type]::GetTypeFromProgID('V83.COMConnector')
}

function Set-SessionEnvironment {
    param(
        $Connection,
        [string]$UserName,
        [string]$UserPassword
    )

    if ($Connection.InfoBasePath) {
        $env:ONEC_IB_PATH = $Connection.InfoBasePath
        Remove-Item Env:ONEC_SERVER -ErrorAction SilentlyContinue
        Remove-Item Env:ONEC_REF -ErrorAction SilentlyContinue
    }
    else {
        $env:ONEC_SERVER = $Connection.Server
        $env:ONEC_REF = $Connection.Ref
        Remove-Item Env:ONEC_IB_PATH -ErrorAction SilentlyContinue
    }

    $env:ONEC_USER = $UserName
    $env:ONEC_PASSWORD = $UserPassword

    Save-OneCSessionFile -Connection $Connection -UserName $UserName -UserPassword $UserPassword
}

function Save-OneCSessionFile {
    param(
        $Connection,
        [string]$UserName,
        [string]$UserPassword
    )

    $sessionPath = Join-Path $ProjectRoot '.onec-session.json'
    $payload = [ordered]@{
        user = $UserName
        password = $UserPassword
    }

    if ($Connection.InfoBasePath) {
        $payload.info_base_path = $Connection.InfoBasePath
        $payload.server = ''
        $payload.ref = ''
    }
    else {
        $payload.info_base_path = ''
        $payload.server = $Connection.Server
        $payload.ref = $Connection.Ref
    }

    ($payload | ConvertTo-Json -Depth 3) | Out-File -LiteralPath $sessionPath -Encoding UTF8
}

Write-Step "1C Analyst — расследование ошибок"
Write-Host "Проект: $ProjectRoot"

$connection = Select-InfoBase -PresetPath $InfoBasePath
if (-not $Server -and $connection.Server) { $Server = $connection.Server }
if (-not $Ref -and $connection.Ref) { $Ref = $connection.Ref }
if (-not $InfoBasePath -and $connection.InfoBasePath) { $InfoBasePath = $connection.InfoBasePath }

if (-not $User) {
    $User = Read-Host "Пользователь 1С"
}
if ($null -eq $Password) {
    $Password = Read-SecurePasswordPlain
}

Set-SessionEnvironment -Connection $connection -UserName $User -UserPassword $Password

Write-Step "Проверка COM-коннектора"
if (-not (Test-ComRegistered)) {
    Write-Host "COM не зарегистрирован. Запуск Register-1CCom.ps1 (может потребоваться UAC)..."
    & $RegisterComScript
}

Write-Step "Проверка подключения к базе"
$testArgs = @('-AgentMode', '-Query', 'ВЫБРАТЬ 1 КАК Connected', '-MaxRows', '1')
if ($InfoBasePath) { $testArgs += @('-InfoBasePath', $InfoBasePath) }
else { $testArgs += @('-Server', $Server, '-Ref', $Ref) }
$testArgs += @('-User', $User)
if ($Password) { $testArgs += @('-Password', $Password) }

$testJson = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $GetDataScript @testArgs
Write-Host "Подключение OK."

if (-not $Problem) {
    Write-Step "Описание проблемы"
    Write-Host "Опишите симптом (можно несколько строк). Пустая строка — завершить ввод."
    $lines = @()
    while ($true) {
        $line = Read-Host ">"
        if ([string]::IsNullOrWhiteSpace($line)) { break }
        $lines += $line
    }
    $Problem = ($lines -join [Environment]::NewLine).Trim()
}

if ([string]::IsNullOrWhiteSpace($Problem)) {
    throw "Описание проблемы не задано."
}

$promptFile = Join-Path $ProjectRoot 'session-prompt.md'
@(
    "# Задача аналитика 1С",
    "",
    $Problem,
    "",
    "## Контекст подключения",
    "- База: $(if ($InfoBasePath) { $InfoBasePath } else { "$Server / $Ref" })",
    "- Пользователь: $User",
    "",
    "Подключение к базе уже сохранено (.onec-session.json).",
    "Сначала onec_connection_status, затем onec_query. Не предлагай Start-1CAnalyst.ps1."
) | Out-File -LiteralPath $promptFile -Encoding UTF8

Write-Step "Стартовый промпт сохранён: session-prompt.md"

if ($SkipOpenCode) {
    Write-Host "SkipOpenCode: OpenCode не запускался. Env ONEC_* установлены в текущей сессии."
    exit 0
}

$opencode = Get-OpenCodeCommand
if (-not $opencode) {
    Write-Host ""
    Write-Host "OpenCode не найден в PATH." -ForegroundColor Yellow
    Write-Host "Установите: npm install -g opencode-ai  (или см. https://opencode.ai)"
    Write-Host "Затем в каталоге проекта выполните:"
    Write-Host "  cd `"$ProjectRoot`""
    Write-Host "  opencode"
    Write-Host ""
    Write-Host "Передайте агенту содержимое session-prompt.md и выберите agent 1c-analyst."
    exit 0
}

Write-Step "Запуск OpenCode (agent: 1c-analyst)"

function Show-SessionWelcome {
    $welcomeScript = Join-Path $ProjectRoot 'mcp\Print-Welcome.ps1'
    if (Test-Path -LiteralPath $welcomeScript) {
        try {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $welcomeScript
        }
        catch {
            Write-Host "Подсказка: в чате OpenCode агент покажет возможности через onec_welcome." -ForegroundColor Yellow
        }
    }
}

Show-SessionWelcome
Write-Host ""
Write-Host "В чате выберите агент 1c-analyst. При новой сессии он выведет список функций (onec_welcome)."
Write-Host ""

Set-Location $ProjectRoot

$localConfig = Join-Path $ProjectRoot 'opencode.local.json'
if (Test-Path -LiteralPath $localConfig) {
    $env:OPENCODE_CONFIG = $localConfig
}

& $opencode
